#!/usr/bin/env python3
"""Import analyses for calibration points from a CSV file."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import django

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "calimag.settings")
django.setup()

from django.db import transaction  # noqa: E402  pylint: disable=wrong-import-position
from django.utils import timezone  # noqa: E402  pylint: disable=wrong-import-position

from app.cadastro.models import Instrumento  # noqa: E402  pylint: disable=wrong-import-position
from app.instrumento.models import (  # noqa: E402  pylint: disable=wrong-import-position
    CertificadoCalibracao,
    PontoCalibracao,
    StatusPontoCalibracao,
)

DATE_FORMATS = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M",
]

MANDATORY_ALIASES = {
    "sequencia": {"sequencia", "seq"},
    "codigo": {"codigo", "instrumento", "cod"},
    "tendencia": {"tendencia", "trend"},
    "incerteza": {"incerteza", "certeza", "uncertainty"},
    "data_analise": {"dataanalise", "data", "analise"},
    "resultado": {"resultado", "result"},
}
OPTIONAL_ALIASES = {
    "observacoes": {"observacoes", "obs"},
}


@dataclass
class CsvRecord:
    line: int
    codigo: str
    sequencia: int
    tendencia: Optional[str]
    incerteza: Optional[Decimal]
    data_analise: timezone.datetime
    resultado: Optional[str]
    observacoes: Optional[str]


def detect_delimiter(sample_line: str) -> str:
    if not sample_line:
        return ","
    candidates = [(",", sample_line.count(",")), (";", sample_line.count(";")), ("\t", sample_line.count("\t")), ("|", sample_line.count("|"))]
    delimiter, hits = max(candidates, key=lambda item: item[1])
    return delimiter if hits > 0 else ","


def load_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Unable to decode CSV with utf-8 or latin-1.")


def normalize(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def resolve_indexes(row: Sequence[str]) -> dict:
    normalized = [normalize(cell) for cell in row]
    indexes = {}
    for key, aliases in {**MANDATORY_ALIASES, **OPTIONAL_ALIASES}.items():
        idx = next((i for i, name in enumerate(normalized) if name in aliases), None)
        if idx is not None:
            indexes[key] = idx
    return indexes


def parse_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    raw = value.replace('.', '').replace(',', '.') if isinstance(value, str) else str(value)
    raw = raw.strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_date(value: Optional[str]) -> Optional[timezone.datetime]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            parsed = dt.datetime.strptime(raw, fmt)
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            return parsed
        except ValueError:
            continue
    return None


def iter_rows(reader: Iterable[Sequence[str]]) -> Iterable[tuple[int, List[str]]]:
    for line_number, row in enumerate(reader, start=1):
        if not row:
            continue
        if not any((cell or "").strip() for cell in row):
            continue
        yield line_number, [cell.strip() for cell in row]


def parse_csv(path: Path, delimiter: Optional[str]) -> List[CsvRecord]:
    text = load_text(path)
    sample_line = next((line for line in text.splitlines() if line.strip()), "")
    csv_delimiter = delimiter or detect_delimiter(sample_line)
    reader = csv.reader(io.StringIO(text), delimiter=csv_delimiter)

    records: List[CsvRecord] = []
    indexes = None
    for line_number, row in iter_rows(reader):
        if indexes is None:
            indexes = resolve_indexes(row)
            required = {"sequencia", "codigo", "resultado", "data_analise"}
            if required.issubset(indexes.keys()):
                continue  # header
            indexes = {"sequencia": 0, "codigo": 1, "tendencia": 2, "incerteza": 3, "data_analise": 4, "resultado": 5}
        sequencia_raw = row[indexes["sequencia"]] if len(row) > indexes["sequencia"] else ""
        codigo = row[indexes["codigo"]] if len(row) > indexes["codigo"] else ""
        tendencia = row[indexes["tendencia"]] if indexes.get("tendencia") is not None and len(row) > indexes["tendencia"] else None
        incerteza_raw = row[indexes["incerteza"]] if indexes.get("incerteza") is not None and len(row) > indexes["incerteza"] else None
        data_raw = row[indexes["data_analise"]] if len(row) > indexes["data_analise"] else ""
        resultado = row[indexes["resultado"]] if len(row) > indexes["resultado"] else ""
        observacoes = None
        obs_idx = indexes.get("observacoes")
        if obs_idx is not None and len(row) > obs_idx:
            observacoes = row[obs_idx]

        if not codigo or not sequencia_raw:
            raise ValueError(f"Linha {line_number}: codigo e sequencia sao obrigatorios")
        try:
            sequencia = int(sequencia_raw)
        except ValueError as exc:
            raise ValueError(f"Linha {line_number}: sequencia invalida ({sequencia_raw})") from exc
        data_analise = parse_date(data_raw) or timezone.now()
        incerteza = parse_decimal(incerteza_raw)
        records.append(
            CsvRecord(
                line=line_number,
                codigo=codigo,
                sequencia=sequencia,
                tendencia=tendencia,
                incerteza=incerteza,
                data_analise=data_analise,
                resultado=resultado.strip() or None,
                observacoes=observacoes,
            )
        )
    return records


def register_analysis(record: CsvRecord, dry_run: bool) -> None:
    instrumento = Instrumento.objects.filter(codigo__iexact=record.codigo.strip()).first()
    if not instrumento:
        raise ValueError(f"Instrumento '{record.codigo}' nao encontrado")
    ponto = PontoCalibracao.objects.filter(instrumento=instrumento, sequencia=record.sequencia).first()
    if not ponto:
        raise ValueError(f"Ponto sequencia {record.sequencia} nao encontrado para instrumento {instrumento.codigo}")
    last_cert = CertificadoCalibracao.objects.filter(status__instrumento=instrumento).order_by('-data_criacao').first()
    if dry_run:
        print(
            f"[DRY-RUN] Ponto seq {record.sequencia} ({instrumento.codigo}) -> resultado {record.resultado or '-'}"
        )
        return
    with transaction.atomic():
        status = StatusPontoCalibracao.objects.create(
            ponto_calibracao=ponto,
            incerteza=record.incerteza,
            tendencia=record.tendencia or '',
            resultado=(record.resultado.lower() if record.resultado else None),
            observacoes=record.observacoes or '',
            certificado=last_cert,
        )
        status.data_criacao = record.data_analise
        status.save(update_fields=['data_criacao'])
    print(
        f"OK linha {record.line}: seq {record.sequencia} ({instrumento.codigo}) salvo com resultado {record.resultado or '-'}"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importa análises de pontos de calibração a partir de um CSV.")
    parser.add_argument("csv_path", type=Path, help="Arquivo CSV com colunas sequencia,codigo,tendencia,incerteza,data_analise,resultado")
    parser.add_argument("--delimiter", dest="delimiter", help="Delimitador (auto detect quando omitido)")
    parser.add_argument("--dry-run", action="store_true", help="Valida sem gravar no banco")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not args.csv_path.exists():
        parser.error(f"Arquivo {args.csv_path} nao encontrado")

    records = parse_csv(args.csv_path, args.delimiter)
    if not records:
        print("Nenhuma linha valida encontrada.")
        return

    success = 0
    failures: List[str] = []
    for record in records:
        try:
            register_analysis(record, args.dry_run)
            success += 1
        except Exception as exc:  # pylint: disable=broad-except
            failures.append(f"Linha {record.line}: {exc}")
            print(f"ERRO linha {record.line}: {exc}")

    print("")
    print(f"Processadas: {len(records)} | Sucesso: {success} | Falhas: {len(failures)}")
    if failures:
        print("Falhas detalhadas:")
        for item in failures:
            print(f" - {item}")


if __name__ == "__main__":
    main()

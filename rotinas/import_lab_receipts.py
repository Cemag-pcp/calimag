#!/usr/bin/env python3
"""Bulk receiver of instruments from laboratories based on a CSV file."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import os
import sys
from dataclasses import dataclass
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
    StatusInstrumento,
)

DATE_FORMATS = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y %H:%M",
    "%Y-%m-%d %H:%M",
]

MANDATORY_ALIASES = {
    "sequencia": {"sequencia", "seq", "linha"},
    "codigo": {"codigo", "instrumento", "cod", "instrument"},
    "data_recebimento": {"datarecebimento", "data", "recebimento"},
}
OPTIONAL_ALIASES = {
    "link": {"link", "linkcertificado", "certificado", "url"},
    "laboratorio": {"laboratorio", "lab", "laboratory"},
    "observacoes": {"observacoes", "obs", "comentario"},
}


@dataclass
class CsvRecord:
    line: int
    codigo: str
    link: str
    recebimento: timezone.datetime
    laboratorio: str
    observacoes: str


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
            required = {"codigo", "data_recebimento"}
            if required.issubset(indexes.keys()):
                # header row, skip
                continue
            # assume no header, default order
            indexes = {
                "codigo": 1 if len(row) > 1 else 0,
                "link": 2 if len(row) > 2 else 1,
                "data_recebimento": 3 if len(row) > 3 else 2,
            }
        codigo = row[indexes["codigo"]] if len(row) > indexes["codigo"] else ""
        link = ""
        link_idx = indexes.get("link")
        if link_idx is not None and len(row) > link_idx:
            link = row[link_idx]
        raw_date = row[indexes["data_recebimento"]] if len(row) > indexes["data_recebimento"] else ""
        recebimento = parse_date(raw_date) or timezone.now()
        laboratorio = ""
        obs = ""
        lab_idx = indexes.get("laboratorio")
        obs_idx = indexes.get("observacoes")
        if lab_idx is not None and len(row) > lab_idx:
            laboratorio = row[lab_idx]
        if obs_idx is not None and len(row) > obs_idx:
            obs = row[obs_idx]
        if not codigo:
            raise ValueError(f"Linha {line_number}: codigo e obrigatorio")
        records.append(CsvRecord(line=line_number, codigo=codigo, link=link, recebimento=recebimento, laboratorio=laboratorio, observacoes=obs))
    return records


def register_receipt(record: CsvRecord, dry_run: bool) -> None:
    instrumento = Instrumento.objects.filter(codigo__iexact=record.codigo.strip()).first()
    if not instrumento:
        raise ValueError(f"Instrumento '{record.codigo}' nao encontrado")
    lab_name = record.laboratorio.strip() or "externo"
    if dry_run:
        print(f"[DRY-RUN] {instrumento.codigo} recebido em {record.recebimento.date()} (lab {lab_name})")
        return
    with transaction.atomic():
        last_sent = (
            StatusInstrumento.objects.filter(
                instrumento=instrumento,
                tipo_status__startswith='Enviado ao laborat',
                data_recebimento__isnull=True,
            )
            .order_by('-data_entrega')
            .first()
        )
        if last_sent:
            last_sent.data_recebimento = record.recebimento
            last_sent.data_devolucao = record.recebimento
            last_sent.save(update_fields=['data_recebimento', 'data_devolucao'])
        status = StatusInstrumento.objects.create(
            instrumento=instrumento,
            funcionario=None,
            data_entrega=timezone.now(),
            data_devolucao=None,
            data_recebimento=record.recebimento,
            observacoes=(record.observacoes or f'Importacao CSV - Recebido do lab {lab_name}'),
            tipo_status=f'Recebido do laboratorio {lab_name}',
        )
        if record.link.strip():
            CertificadoCalibracao.objects.create(status=status, link=record.link.strip())
    print(f"OK linha {record.line}: {instrumento.codigo} recebido ({lab_name})")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importa recebimentos de laboratório a partir de um CSV.")
    parser.add_argument("csv_path", type=Path, help="Arquivo CSV com colunas codigo, data_recebimento e link_certificado opcional")
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
            register_receipt(record, args.dry_run)
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

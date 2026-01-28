#!/usr/bin/env python3
"""Bulk sender of instruments to laboratories based on a CSV file."""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence
import datetime as dt

import django

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "calimag.settings")
django.setup()

from django.db import transaction  # noqa: E402  pylint: disable=wrong-import-position
from django.utils import timezone  # noqa: E402  pylint: disable=wrong-import-position

from app.cadastro.models import Instrumento, Laboratorio  # noqa: E402  pylint: disable=wrong-import-position
from app.instrumento.models import (  # noqa: E402  pylint: disable=wrong-import-position
    FuncionarioInstrumento,
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
    "instrumento": {"instrumento", "codigo", "instrumentocodigo", "codigoinstrumento", "instrument"},
    "laboratorio": {"laboratorio", "lab", "laboratory"},
    "data_envio": {"dataenvio", "data", "envio", "dataentrega"},
}


@dataclass
class CsvRecord:
    line: int
    instrumento: str
    laboratorio: str
    envio: timezone.datetime


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


def normalize(column: str) -> str:
    return "".join(ch for ch in column.lower() if ch.isalnum())


def resolve_indexes(sample_row: Sequence[str]) -> dict:
    normalized = [normalize(cell) for cell in sample_row]
    indexes = {}
    for key, aliases in MANDATORY_ALIASES.items():
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


def parse_csv(path: Path, default_date: Optional[timezone.datetime], delimiter: Optional[str]) -> List[CsvRecord]:
    text = load_text(path)
    sample_line = next((line for line in text.splitlines() if line.strip()), "")
    csv_delimiter = delimiter or detect_delimiter(sample_line)
    reader = csv.reader(io.StringIO(text), delimiter=csv_delimiter)

    records: List[CsvRecord] = []
    indexes = None
    for line_number, row in iter_rows(reader):
        if indexes is None:
            indexes = resolve_indexes(row)
            if "instrumento" in indexes and "laboratorio" in indexes:
                # Header detected; move to next row
                missing = set(MANDATORY_ALIASES.keys()) - set(indexes.keys())
                if missing:
                    indexes["data_envio"] = None
                continue
            # No header, assume default layout
            indexes = {"instrumento": 0, "laboratorio": 1, "data_envio": 2 if len(row) > 2 else None}
        instrumento = row[indexes["instrumento"]] if len(row) > indexes["instrumento"] else ""
        laboratorio = row[indexes["laboratorio"]] if len(row) > indexes["laboratorio"] else ""
        raw_date = row[indexes["data_envio"]] if indexes.get("data_envio") is not None and len(row) > indexes["data_envio"] else ""
        send_date = parse_date(raw_date) or default_date or timezone.now()
        records.append(CsvRecord(line=line_number, instrumento=instrumento, laboratorio=laboratorio, envio=send_date))
    return records


def ensure_laboratorio(name: str) -> Laboratorio:
    lab = Laboratorio.objects.filter(nome__iexact=name.strip()).first()
    if lab:
        return lab
    return Laboratorio.objects.create(nome=name.strip() or "externo")


def close_open_statuses(instrumento: Instrumento, timestamp: timezone.datetime) -> None:
    FuncionarioInstrumento.objects.filter(instrumento=instrumento, ativo=True).update(ativo=False, data_fim=timestamp)
    StatusInstrumento.objects.filter(instrumento=instrumento, data_devolucao__isnull=True).update(data_devolucao=timestamp)
    last_without_receb = (
        StatusInstrumento.objects.filter(instrumento=instrumento, data_recebimento__isnull=True)
        .order_by("-data_entrega")
        .first()
    )
    if last_without_receb and not last_without_receb.data_recebimento:
        last_without_receb.data_recebimento = timestamp
        last_without_receb.save(update_fields=["data_recebimento"])


def register_send(record: CsvRecord, dry_run: bool) -> None:
    instrumento = Instrumento.objects.filter(codigo__iexact=record.instrumento.strip()).first()
    if not instrumento:
        raise ValueError(f"Instrumento '{record.instrumento}' nao encontrado")
    lab = ensure_laboratorio(record.laboratorio)
    if dry_run:
        print(f"[DRY-RUN] {instrumento.codigo} -> {lab.nome} ({record.envio.isoformat()})")
        return
    with transaction.atomic():
        close_open_statuses(instrumento, record.envio)
        StatusInstrumento.objects.create(
            instrumento=instrumento,
            funcionario=None,
            data_entrega=record.envio,
            data_devolucao=None,
            data_recebimento=None,
            observacoes=f"Importacao CSV - Lab: {lab.nome}",
            tipo_status=f"Enviado ao laboratorio {lab.nome}",
        )
    print(f"OK linha {record.line}: {instrumento.codigo} enviado para {lab.nome} em {record.envio.date()}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Importa envios para laboratorio a partir de um CSV.")
    parser.add_argument("csv_path", type=Path, help="Caminho do arquivo CSV com as colunas instrumento,laboratorio,data_envio")
    parser.add_argument("--delimiter", dest="delimiter", help="Delimitador da planilha (detectado automaticamente quando omitido)")
    parser.add_argument(
        "--default-date",
        dest="default_date",
        help="Data padrao (dd/mm/aaaa) usada quando a coluna data_envio estiver vazia",
    )
    parser.add_argument("--dry-run", action="store_true", help="Apenas valida o arquivo sem gravar no banco")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    if not args.csv_path.exists():
        parser.error(f"Arquivo {args.csv_path} nao encontrado")

    default_date = parse_date(args.default_date) if args.default_date else None
    if args.default_date and default_date is None:
        parser.error("Nao foi possivel interpretar --default-date. Use formatos como 18/02/2025.")

    records = parse_csv(args.csv_path, default_date, args.delimiter)
    if not records:
        print("Nenhuma linha valida encontrada.")
        return

    success = 0
    failures: List[str] = []
    for record in records:
        try:
            register_send(record, args.dry_run)
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

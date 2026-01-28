#!/usr/bin/env python
"""Rotina para importar Pontos de Calibracao via CSV."""
from __future__ import annotations

import argparse
import csv
import os
import sys
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

import django
from django.db import transaction

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'calimag.settings')
django.setup()

from app.cadastro.models import Instrumento, PontoCalibracao  # noqa: E402  pylint: disable=wrong-import-position


CSV_COLUMNS = {
    'sequencia': {'aliases': {'seq', 'sequencia'}},
    'codigo': {'aliases': {'codigo', 'instrumento'}},
    'descricao': {'aliases': {'descricao', 'nome'}},
    'nominal_min': {'aliases': {'nominal_min', 'valor_min', 'valor_minimo'}},
    'nominal_max': {'aliases': {'nominal_max', 'valor_max', 'valor_maximo'}},
    'tolerancia_min': {'aliases': {'tolerancia_min', 'tolerancia_menos'}},
    'tolerancia_max': {'aliases': {'tolerancia_max', 'tolerancia_mais'}},
    'unidade': {'aliases': {'unidade', 'unit'}},
    'periodicidade': {'aliases': {'periodicidade', 'periodicidade_dias', 'periodo'}},
}


def strip_accents(text: str) -> str:
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def normalize_key(key: str) -> str:
    base = strip_accents(key.strip().lower())
    for canonical, meta in CSV_COLUMNS.items():
        if base in meta['aliases']:
            return canonical
    return base


def parse_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    value = value.strip().replace(',', '.')
    if value == '':
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def parse_int(value: str | None, default: int | None = None) -> int | None:
    if value is None:
        return default
    value = value.strip()
    if not value:
        return default
    try:
        return int(Decimal(value))
    except (InvalidOperation, ValueError):
        return default


def clean_row(row: dict[str, str | None]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, val in row.items():
        if key is None:
            continue
        cleaned_key = normalize_key(key)
        cleaned[cleaned_key] = (val or '').strip()
    return cleaned


def calc_valor_nominal(min_value: Decimal | None, max_value: Decimal | None) -> Decimal | None:
    if min_value is not None and max_value is not None:
        return (min_value + max_value) / 2
    return min_value or max_value


def upsert_ponto(instrumento: Instrumento, sequencia: int, payload: dict[str, object]) -> tuple[bool, bool]:
    ponto, created = PontoCalibracao.objects.get_or_create(
        instrumento=instrumento,
        sequencia=sequencia,
        defaults=payload,
    )
    if created:
        return True, False

    changed = False
    for field, value in payload.items():
        if getattr(ponto, field) != value:
            setattr(ponto, field, value)
            changed = True

    if changed:
        ponto.save(update_fields=list(payload.keys()))
    return False, changed


def detect_delimiter(first_line: str) -> str:
    if '\t' in first_line:
        return '\t'
    semicolon_count = first_line.count(';')
    comma_count = first_line.count(',')
    if semicolon_count > comma_count:
        return ';'
    return ','


def process_csv(csv_path: Path) -> tuple[int, int, int, int]:
    created = updated = skipped = errors = 0

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        first_line = handle.readline()
        delimiter = detect_delimiter(first_line) if first_line else ','
        handle.seek(0)
        reader = csv.DictReader(handle, delimiter=delimiter)

        if not reader.fieldnames:
            raise ValueError('CSV sem cabecalho encontrado.')

        with transaction.atomic():
            for idx, row in enumerate(reader, start=2):
                try:
                    normalized = clean_row(row)
                    codigo = normalized.get('codigo')
                    seq_val = parse_int(normalized.get('sequencia'))

                    if not codigo or seq_val is None:
                        skipped += 1
                        print(f'[linha {idx}] ignorada: codigo ou sequencia ausentes.')
                        continue

                    instrumento = Instrumento.objects.filter(codigo=codigo).first()
                    if instrumento is None:
                        skipped += 1
                        print(f'[linha {idx}] ignorada: instrumento "{codigo}" nao encontrado.')
                        continue

                    descricao = normalized.get('descricao') or ''
                    valor_min = parse_decimal(normalized.get('nominal_min'))
                    valor_max = parse_decimal(normalized.get('nominal_max'))
                    unidade = normalized.get('unidade') or 'outro'
                    periodicidade = parse_int(normalized.get('periodicidade'), default=365) or 365
                    tolerancia_menos = parse_decimal(normalized.get('tolerancia_min'))
                    tolerancia_mais = parse_decimal(normalized.get('tolerancia_max'))

                    valor_nominal = calc_valor_nominal(valor_min, valor_max)

                    payload = {
                        'descricao': descricao or f'Ponto {seq_val}',
                        'valor_minimo': valor_min,
                        'valor_maximo': valor_max,
                        'valor_nominal': valor_nominal,
                        'unidade': unidade,
                        'periodicidade_calibracao': periodicidade,
                        'tolerancia_menos': tolerancia_menos,
                        'tolerancia_mais': tolerancia_mais,
                        'ativo': True,
                    }

                    was_created, was_updated = upsert_ponto(instrumento, seq_val, payload)
                    if was_created:
                        created += 1
                    elif was_updated:
                        updated += 1
                    else:
                        skipped += 1
                except Exception as exc:  # pylint: disable=broad-except
                    errors += 1
                    print(f'[linha {idx}] erro inesperado: {exc}')

    return created, updated, skipped, errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Importa pontos de calibracao associados a instrumentos existentes. '
            'O CSV deve conter "codigo" e "sequencia" e pode incluir '
            '"descricao", "nominal_min", "nominal_max", "tolerancia_min", '
            '"tolerancia_max", "unidade" e "periodicidade".'
        )
    )
    parser.add_argument('csv_path', help='Caminho para o arquivo CSV contendo os pontos.')
    args = parser.parse_args()

    csv_file = Path(args.csv_path).expanduser().resolve()
    if not csv_file.exists():
        parser.error(f'Arquivo nao encontrado: {csv_file}')

    created, updated, skipped, errors = process_csv(csv_file)
    print('\nResumo:')
    print(f'  Criados : {created}')
    print(f'  Atualizados : {updated}')
    print(f'  Ignorados : {skipped}')
    print(f'  Erros : {errors}')


if __name__ == '__main__':
    main()

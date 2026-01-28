#!/usr/bin/env python
"""Rotina para importar Tipos de Instrumento a partir de um CSV."""
from __future__ import annotations

import argparse
import csv
import os
import sys
import unicodedata
from pathlib import Path

import django
from django.db import transaction

# garante que o projeto esteja no sys.path antes de carregar o Django
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'calimag.settings')
django.setup()

from app.cadastro.models import TipoInstrumento  # noqa: E402  pylint: disable=wrong-import-position


def strip_accents(text: str) -> str:
    """Remove acentos para facilitar comparacoes ascii."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def parse_bool(value: str | None) -> bool:
    """Converte valores textuais em booleanos, padrao True."""
    if value is None:
        return True
    normalized = value.strip().lower()
    normalized_ascii = strip_accents(normalized)
    if normalized_ascii in {'', '1', 'true', 't', 'yes', 'sim'}:
        return True
    if normalized_ascii in {'0', 'false', 'f', 'no', 'nao'}:
        return False
    return True


def clean_row(row: dict[str, str | None]) -> dict[str, str]:
    """Normaliza chaves para minusculas sem acento e remove espacos extras."""
    cleaned: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        lowered = key.strip().lower()
        cleaned_key = strip_accents(lowered)
        cleaned[cleaned_key] = (value or '').strip()
    return cleaned


def process_csv(csv_path: Path) -> tuple[int, int, int]:
    """Processa o CSV e retorna tupla (criadas, atualizadas, ignoradas)."""
    created = updated = skipped = 0

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('CSV sem cabecalho encontrado.')

        with transaction.atomic():
            for idx, row in enumerate(reader, start=2):  # considera cabecalho na linha 1
                normalized = clean_row(row)
                descricao = normalized.get('descricao')
                if not descricao:
                    skipped += 1
                    print(f'[linha {idx}] ignorada: campo "descricao" vazio.')
                    continue

                documento = normalized.get('documento_qualidade') or normalized.get('documento') or ''
                ativo = parse_bool(normalized.get('ativo'))

                tipo, created_flag = TipoInstrumento.objects.get_or_create(
                    descricao=descricao,
                    defaults={
                        'documento_qualidade': documento,
                        'ativo': ativo,
                    },
                )

                if created_flag:
                    created += 1
                    continue

                changed = False
                if documento and tipo.documento_qualidade != documento:
                    tipo.documento_qualidade = documento
                    changed = True
                if tipo.ativo != ativo:
                    tipo.ativo = ativo
                    changed = True

                if changed:
                    tipo.save(update_fields=['documento_qualidade', 'ativo'])
                    updated += 1
                else:
                    skipped += 1

    return created, updated, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Importa registros de TipoInstrumento. '
            'O CSV deve conter a coluna "descricao" e opcionalmente '
            '"documento_qualidade" e "ativo".'
        )
    )
    parser.add_argument('csv_path', help='Caminho para o arquivo CSV a ser processado.')
    args = parser.parse_args()

    csv_file = Path(args.csv_path).expanduser().resolve()
    if not csv_file.exists():
        parser.error(f'Arquivo nao encontrado: {csv_file}')

    created, updated, skipped = process_csv(csv_file)
    print('\nResumo:')
    print(f'  Criados : {created}')
    print(f'  Atualizados : {updated}')
    print(f'  Ignorados : {skipped}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python
"""Rotina para importar Setores a partir de um CSV."""
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

from app.cadastro.models import Setor  # noqa: E402  pylint: disable=wrong-import-position


def strip_accents(text: str) -> str:
    """Remove acentos para facilitar comparacoes."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def normalize_header(text: str) -> str:
    """Normaliza cabecalho para minusculas ascii."""
    return strip_accents(text.strip().lower())


def normalize_setor_name(value: str | None) -> str:
    """Normaliza o nome do setor removendo espacos excedentes."""
    if not value:
        return ''
    return ' '.join(str(value).replace('\xa0', ' ').strip().split())


def comparison_key(value: str) -> str:
    """Gera uma chave canonica para comparacao sem acentos e case insensitive."""
    return strip_accents(normalize_setor_name(value)).lower()


def process_csv(csv_path: Path) -> tuple[int, int]:
    """Processa o CSV e retorna (criados, ignorados)."""
    created = skipped = 0

    existing_by_key = {
        comparison_key(nome): setor_id
        for setor_id, nome in Setor.objects.values_list('id', 'nome')
    }

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('CSV sem cabecalho encontrado.')

        setor_column = None
        for fieldname in reader.fieldnames:
            if fieldname and normalize_header(fieldname) == 'setor':
                setor_column = fieldname
                break

        if setor_column is None:
            raise ValueError('CSV nao contem a coluna "setor".')

        seen_in_file: set[str] = set()

        with transaction.atomic():
            for idx, row in enumerate(reader, start=2):
                raw_name = row.get(setor_column)
                nome = normalize_setor_name(raw_name)
                if not nome:
                    skipped += 1
                    print(f'[linha {idx}] ignorada: campo "setor" vazio.')
                    continue

                key = comparison_key(nome)
                if key in seen_in_file:
                    skipped += 1
                    continue
                seen_in_file.add(key)

                if key in existing_by_key:
                    skipped += 1
                    continue

                setor = Setor.objects.create(nome=nome, ativo=True)
                existing_by_key[key] = setor.id
                created += 1

    return created, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Importa registros de Setor a partir de um CSV contendo a coluna "setor".'
    )
    parser.add_argument('csv_path', help='Caminho para o arquivo CSV a ser processado.')
    args = parser.parse_args()

    csv_file = Path(args.csv_path).expanduser().resolve()
    if not csv_file.exists():
        parser.error(f'Arquivo nao encontrado: {csv_file}')

    created, skipped = process_csv(csv_file)
    print('\nResumo:')
    print(f'  Criados : {created}')
    print(f'  Ignorados : {skipped}')


if __name__ == '__main__':
    main()

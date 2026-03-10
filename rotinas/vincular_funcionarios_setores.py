#!/usr/bin/env python
"""Vincula funcionarios aos setores a partir de um CSV."""
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

from app.cadastro.models import Funcionario, Setor  # noqa: E402  pylint: disable=wrong-import-position


def strip_accents(text: str) -> str:
    """Remove acentos para facilitar comparacoes."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def normalize_header(text: str) -> str:
    """Normaliza cabecalho para minusculas ascii."""
    return strip_accents((text or '').strip().lower())


def normalize_name(value: str | None) -> str:
    """Remove espacos excedentes do nome."""
    if not value:
        return ''
    return ' '.join(str(value).replace('\xa0', ' ').strip().split())


def normalize_code(value: str | None) -> str:
    """Converte codigo/matricula em chave numerica sem zeros a esquerda."""
    digits = ''.join(ch for ch in str(value or '').strip() if ch.isdigit())
    if not digits:
        return ''
    return digits.lstrip('0') or '0'


def process_csv(csv_path: Path) -> tuple[int, int, int, int]:
    """Processa o CSV e retorna (atualizados, sem_alteracao, sem_funcionario, sem_setor)."""
    updated = unchanged = missing_funcionario = missing_setor = 0

    funcionarios_by_code = {
        normalize_code(matricula): funcionario_id
        for funcionario_id, matricula in Funcionario.objects.values_list('id', 'matricula')
    }
    setores_by_name = {
        normalize_name(nome): setor_id
        for setor_id, nome in Setor.objects.values_list('id', 'nome')
    }

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('CSV sem cabecalho encontrado.')

        with transaction.atomic():
            for idx, row in enumerate(reader, start=2):
                cleaned = {
                    normalize_header(key): (value or '').strip()
                    for key, value in row.items()
                    if key is not None
                }

                matricula_key = normalize_code(cleaned.get('codigo'))
                setor_nome = normalize_name(cleaned.get('setor'))

                if not matricula_key or not setor_nome:
                    unchanged += 1
                    continue

                funcionario_id = funcionarios_by_code.get(matricula_key)
                if funcionario_id is None:
                    missing_funcionario += 1
                    print(f'[linha {idx}] funcionario nao encontrado para matricula "{matricula_key}".')
                    continue

                setor_id = setores_by_name.get(setor_nome)
                if setor_id is None:
                    missing_setor += 1
                    print(f'[linha {idx}] setor nao encontrado: "{setor_nome}".')
                    continue

                rows = Funcionario.objects.filter(id=funcionario_id).exclude(setor_id=setor_id).update(setor_id=setor_id)
                if rows:
                    updated += 1
                else:
                    unchanged += 1

    return updated, unchanged, missing_funcionario, missing_setor


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Vincula funcionarios aos setores com base nas colunas "codigo" e "setor" do CSV.'
    )
    parser.add_argument('csv_path', help='Caminho para o arquivo CSV a ser processado.')
    args = parser.parse_args()

    csv_file = Path(args.csv_path).expanduser().resolve()
    if not csv_file.exists():
        parser.error(f'Arquivo nao encontrado: {csv_file}')

    updated, unchanged, missing_funcionario, missing_setor = process_csv(csv_file)
    print('\nResumo:')
    print(f'  Atualizados : {updated}')
    print(f'  Sem alteracao : {unchanged}')
    print(f'  Sem funcionario : {missing_funcionario}')
    print(f'  Sem setor : {missing_setor}')


if __name__ == '__main__':
    main()

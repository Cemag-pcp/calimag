#!/usr/bin/env python
"""Rotina para importar Instrumentos a partir de um CSV."""
from __future__ import annotations

import argparse
import csv
import os
import sys
import unicodedata
from datetime import datetime, date
from pathlib import Path

import django
from django.db import transaction

# garante que o projeto esteja no sys.path antes de carregar o Django
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'calimag.settings')
django.setup()

from app.cadastro.models import Instrumento, TipoInstrumento  # noqa: E402  pylint: disable=wrong-import-position

VALID_STATUS = {choice[0]: choice[0] for choice in Instrumento.STATUS_CHOICES}


def strip_accents(text: str) -> str:
    """Remove acentos para facilitar comparacoes ascii."""
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')


def parse_bool(value: str | None, default: bool = False) -> bool:
    """Converte valores textuais em booleanos, permitindo default customizado."""
    if value is None or value == '':
        return default
    normalized = strip_accents(value.strip().lower())
    if normalized in {'1', 'true', 't', 'yes', 'sim'}:
        return True
    if normalized in {'0', 'false', 'f', 'no', 'nao'}:
        return False
    return default


def parse_status(value: str | None, *, fallback: str = 'ativo') -> str:
    """Valida o status informado utilizando o fallback quando necessario."""
    if not value:
        return fallback
    normalized = strip_accents(value.strip().lower())
    # tenta casar com as chaves validas diretamente
    if normalized in VALID_STATUS:
        return normalized
    # tenta casar com o display (segundo elemento) removendo espacos
    for code, label in Instrumento.STATUS_CHOICES:
        if normalized == strip_accents(label).lower():
            return code
    print(f'Aviso: status "{value}" invalido. Usando fallback "{fallback}".')
    return fallback


def parse_date(value: str | None) -> date | None:
    """Tenta converter o texto em data utilizando formatos comuns."""
    if not value:
        return None
    value = value.strip()
    patterns = (
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%m/%d/%Y',
    )
    for fmt in patterns:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(value)
    except ValueError:
        print(f'Aviso: data "{value}" ignorada (formato desconhecido).')
        return None


def parse_int(value: str | None) -> int | None:
    """Converte texto em inteiro, retornando None se inválido."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        print(f'Aviso: valor "{value}" ignorado (inteiro inválido).')
        return None


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


def resolve_tipo(descricao: str | None) -> TipoInstrumento | None:
    """Localiza ou cria o TipoInstrumento correspondente a descricao fornecida."""
    if not descricao:
        return None
    tipo, _ = TipoInstrumento.objects.get_or_create(descricao=descricao)
    return tipo


def process_csv(csv_path: Path) -> tuple[int, int, int, int]:
    """Processa o CSV e retorna (criadas, atualizadas, ignoradas, erros)."""
    created = updated = skipped = errors = 0

    with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError('CSV sem cabecalho encontrado.')

        with transaction.atomic():
            for idx, row in enumerate(reader, start=2):  # considera cabecalho na linha 1
                try:
                    normalized = clean_row(row)
                    codigo = normalized.get('codigo')
                    if not codigo:
                        skipped += 1
                        print(f'[linha {idx}] ignorada: campo requerido "codigo" vazio.')
                        continue

                    descricao_raw = normalized.get('descricao') if 'descricao' in normalized else None

                    tipo_column_present = ('tipo' in normalized) or ('tipoinstrumento' in normalized) or ('tipo_instrumento' in normalized)
                    tipo_desc = normalized.get('tipo') or normalized.get('tipo_instrumento') or normalized.get('tipoinstrumento')
                    tipo = resolve_tipo(tipo_desc) if tipo_desc else None

                    controlado_column_present = ('instrumento_controlado' in normalized) or ('controlado' in normalized)
                    raw_controlado = normalized.get('instrumento_controlado')
                    if raw_controlado is None:
                        raw_controlado = normalized.get('controlado')
                    if controlado_column_present:
                        controlado_value = None if raw_controlado == '' or raw_controlado is None else parse_bool(raw_controlado, default=False)
                    else:
                        controlado_value = None

                    fabricante_present = 'fabricante' in normalized
                    fabricante_value = normalized.get('fabricante') if fabricante_present else None

                    modelo_present = 'modelo' in normalized
                    modelo_value = normalized.get('modelo') if modelo_present else None

                    status_present = 'status' in normalized and normalized.get('status') not in {None, ''}
                    status_value = parse_status(normalized.get('status')) if status_present else None

                    observacoes_present = 'observacoes' in normalized
                    observacoes_value = normalized.get('observacoes') if observacoes_present else None

                    data_present = 'data_aquisicao' in normalized
                    raw_data = normalized.get('data_aquisicao') if data_present else None
                    data_value = parse_date(raw_data) if raw_data else None

                    periodicidade_present = ('periodicidade' in normalized) or ('periodicidade_calibracao' in normalized)
                    raw_periodicidade = normalized.get('periodicidade')
                    if raw_periodicidade is None:
                        raw_periodicidade = normalized.get('periodicidade_calibracao')
                    periodicidade_value = parse_int(raw_periodicidade) if periodicidade_present else None

                    finalidade = 'finalidade' in normalized
                    finalidade_value = normalized.get('finalidade') if finalidade else None

                    instrumento = Instrumento.objects.filter(codigo=codigo).select_related('tipo_instrumento').first()

                    if instrumento is None:
                        Instrumento.objects.create(
                            codigo=codigo,
                            descricao=descricao_raw or '',
                            tipo_instrumento=tipo,
                            instrumento_controlado=controlado_value if controlado_value is not None else False,
                            fabricante=(fabricante_value or ''),
                            modelo=(modelo_value or ''),
                            status=status_value or parse_status(None),
                            observacoes=(observacoes_value or ''),
                            data_aquisicao=data_value,
                            finalidade=finalidade_value,
                            periodicidade_calibracao=periodicidade_value if periodicidade_value is not None else Instrumento._meta.get_field('periodicidade_calibracao').default,
                        )
                        created += 1
                        continue

                    update_data: dict[str, object] = {}

                    if descricao_raw and descricao_raw != instrumento.descricao:
                        update_data['descricao'] = descricao_raw

                    if tipo_column_present:
                        new_tipo_id = tipo.id if tipo else None
                        if instrumento.tipo_instrumento_id != new_tipo_id:
                            update_data['tipo_instrumento_id'] = new_tipo_id

                    if controlado_value is not None and instrumento.instrumento_controlado != controlado_value:
                        update_data['instrumento_controlado'] = controlado_value

                    if fabricante_present:
                        novo_fabricante = (fabricante_value or '')
                        if (instrumento.fabricante or '') != novo_fabricante:
                            update_data['fabricante'] = novo_fabricante

                    if modelo_present:
                        novo_modelo = (modelo_value or '')
                        if (instrumento.modelo or '') != novo_modelo:
                            update_data['modelo'] = novo_modelo

                    if status_present and status_value is not None and instrumento.status != status_value:
                        update_data['status'] = status_value

                    if observacoes_present:
                        novas_observacoes = (observacoes_value or '')
                        if (instrumento.observacoes or '') != novas_observacoes:
                            update_data['observacoes'] = novas_observacoes

                    if data_present:
                        new_date = data_value if raw_data else None
                        if instrumento.data_aquisicao != new_date:
                            update_data['data_aquisicao'] = new_date

                    if periodicidade_present and periodicidade_value is not None:
                        if instrumento.periodicidade_calibracao != periodicidade_value:
                            update_data['periodicidade_calibracao'] = periodicidade_value

                    if update_data:
                        Instrumento.objects.filter(pk=instrumento.pk).update(**update_data)
                        updated += 1
                    else:
                        skipped += 1
                        print(f'[linha {idx}] ignorada: nenhuma alteracao para o codigo "{codigo}".')
                except Exception as exc:  # pylint: disable=broad-except
                    errors += 1
                    print(f'[linha {idx}] erro inesperado: {exc}')

    return created, updated, skipped, errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            'Importa registros de Instrumento. '
            'O CSV deve conter a coluna "codigo" obrigatoriamente, '
            'e opcionalmente "tipo", "instrumento_controlado", "fabricante", '
            '"modelo", "status", "observacoes", "data_aquisicao" e "periodicidade".'
        )
    )
    parser.add_argument('csv_path', help='Caminho para o arquivo CSV a ser processado.')
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

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from django.core.paginator import Paginator
from django.db.models import OuterRef, Subquery, Exists, Count, Q, ExpressionWrapper, F, DateTimeField, DurationField, Value
from django.views.decorators.http import require_GET
from django.db import transaction
from django.utils import timezone

import base64
import csv
import datetime
import io
import json
import math
from datetime import timedelta

from app.cadastro.models import Instrumento, Funcionario, PontoCalibracao
from .models import FuncionarioInstrumento, AssinaturaFuncionarioInstrumento, StatusInstrumento, CertificadoCalibracao, StatusPontoCalibracao
from app.cadastro.models import Laboratorio


def _detect_csv_delimiter(sample_line):
	"""Infer the delimiter used in a CSV sample line."""
	if not sample_line:
		return ','
	candidates = [
		(',', sample_line.count(',')),
		(';', sample_line.count(';')),
		('\t', sample_line.count('\t')),
		('|', sample_line.count('|')),
	]
	delimiter, hits = max(candidates, key=lambda item: item[1])
	return delimiter if hits > 0 else ','


def _parse_csv_datetime(raw_value):
	"""Parse optional datetime/date strings into aware datetimes."""
	if not raw_value:
		return None
	if isinstance(raw_value, datetime.datetime):
		dt = raw_value
	else:
		string_value = str(raw_value).strip()
		if not string_value:
			return None
		dt = parse_datetime(string_value)
		if not dt:
			date_only = parse_date(string_value)
			if date_only:
				dt = datetime.datetime.combine(date_only, datetime.time())
		if not dt:
			return None
	if timezone.is_naive(dt):
		try:
			dt = timezone.make_aware(dt)
		except Exception:
			dt = timezone.make_aware(dt, timezone.get_current_timezone())
	return dt


@login_required
@require_GET
def instrumentos_status_api(request):

	qs = (
		Instrumento.objects
		.filter(status='ativo')
		.select_related('tipo_instrumento')
	)

	# =========================
	# Filtros simples (DB)
	# =========================
	search = (request.GET.get('search') or '').strip()
	if search:
		qs = qs.filter(Q(codigo__icontains=search) | Q(descricao__icontains=search))

	func_search = (request.GET.get('funcionario') or '').strip()
	if func_search:
		func_subquery = StatusInstrumento.objects.filter(
			instrumento=OuterRef('pk')
		).filter(
			Q(funcionario__nome__icontains=func_search) |
			Q(funcionario__matricula__icontains=func_search)
		)
		qs = qs.filter(Exists(func_subquery))

	tipo_id = request.GET.get('tipo_id')
	if tipo_id and tipo_id.isdigit():
		qs = qs.filter(tipo_instrumento_id=int(tipo_id))

	tipo_text = (request.GET.get('tipo') or '').strip()
	if tipo_text:
		qs = qs.filter(tipo_instrumento__descricao__icontains=tipo_text)

	instrumento_controlado = (request.GET.get('instrumento_controlado') or '').lower()
	if instrumento_controlado in {'1', 'true', 'sim', 'yes'}:
		qs = qs.filter(instrumento_controlado=True)
	elif instrumento_controlado in {'0', 'false', 'nao', 'no'}:
		qs = qs.filter(instrumento_controlado=False)

	ids_param = request.GET.get('instrumento_id') or request.GET.get('instrumentos')
	if ids_param:
		ids = [int(i) for i in ids_param.split(',') if i.strip().isdigit()]
		if ids:
			qs = qs.filter(id__in=ids)

	# =========================
	# Subqueries
	# =========================
	latest_status = StatusInstrumento.objects.filter(
		instrumento=OuterRef('pk')
	).order_by('-data_entrega')

	last_envio = StatusInstrumento.objects.filter(
		instrumento=OuterRef('pk'),
		tipo_status__istartswith='Enviado ao laboratório'
	).order_by('-data_entrega')

	last_recebimento = StatusInstrumento.objects.filter(
		instrumento=OuterRef('pk'),
		tipo_status__istartswith='Recebido do laborat',
		data_recebimento__isnull=False
	).order_by('-data_recebimento')

	latest_cert = CertificadoCalibracao.objects.filter(
		status__instrumento=OuterRef('pk')
	).order_by('-data_criacao')

	qs = qs.annotate(
		status_tipo=Subquery(latest_status.values('tipo_status')[:1]),
		status_funcionario=Subquery(latest_status.values('funcionario__nome')[:1]),
		status_funcionario_id=Subquery(latest_status.values('funcionario_id')[:1]),
		status_entrega=Subquery(latest_status.values('data_entrega')[:1]),
		status_devolucao=Subquery(latest_status.values('data_devolucao')[:1]),
		status_recebimento=Subquery(latest_status.values('data_recebimento')[:1]),

		last_envio_data=Subquery(last_envio.values('data_entrega')[:1]),
		last_recebimento_data=Subquery(
			last_recebimento.values('data_recebimento')[:1]
		),

		ultimo_certificado_link=Subquery(latest_cert.values('link')[:1]),

		total_pontos=Count(
			'pontos_calibracao',
			filter=Q(pontos_calibracao__ativo=True),
			distinct=True
		),

		valid_until=ExpressionWrapper(
			F('last_recebimento_data') + ExpressionWrapper(
				F('periodicidade_calibracao') * Value(datetime.timedelta(days=1)),
				output_field=DurationField()
			),
			output_field=DateTimeField()
		),
	)

	validade_inicio = request.GET.get('validade_inicio')
	validade_fim = request.GET.get('validade_fim')

	if validade_inicio:
		start_date = parse_date(validade_inicio)
		if start_date:
			qs = qs.filter(valid_until__date__gte=start_date)

	if validade_fim:
		end_date = parse_date(validade_fim)
		if end_date:
			qs = qs.filter(valid_until__date__lte=end_date)

	# =========================
	# Paginação
	# =========================
	page = int(request.GET.get('page', 1) or 1)
	per_page = max(1, min(int(request.GET.get('per_page', 15) or 15), 200))

	paginator = Paginator(qs.order_by('codigo'), per_page)
	page_obj = paginator.get_page(page)

	today = timezone.now().date()

	items = []
	pending_analysis_count = 0

	for inst in page_obj.object_list:

		# =========================
		# REGRA CORRETA DOS PONTOS
		# =========================
		if inst.total_pontos == 0:
			pontos_ok = True
		else:
			pontos_qs = StatusPontoCalibracao.objects.filter(
				ponto_calibracao__instrumento=inst
			)

			if inst.last_envio_data:
				pontos_qs = pontos_qs.filter(
					data_criacao__gte=inst.last_envio_data
				)

			pontos_ok = (
				pontos_qs
				.values('ponto_calibracao_id')
				.distinct()
				.count()
				>= inst.total_pontos
			)

		if not pontos_ok:
			pending_analysis_count += 1

		last_recebimento = inst.last_recebimento_data
		valid_until = (
			last_recebimento + timedelta(days=inst.periodicidade_calibracao)
			if last_recebimento else None
		)

		if valid_until and valid_until.date() >= today:
			calibration_status = 'em_dia'
		elif valid_until:
			calibration_status = 'atrasado'
		else:
			calibration_status = 'sem_analise'

		items.append({
			'id': inst.id,
			'codigo': inst.codigo,
			'descricao': inst.descricao,
			'tipo': inst.tipo_instrumento.descricao if inst.tipo_instrumento else '',
			'instrumento_controlado': inst.instrumento_controlado,
			'total_pontos': inst.total_pontos,
			'data_ultimo_envio': inst.last_envio_data.isoformat() if inst.last_envio_data else None,
			'primeiro_envio': inst.last_envio_data is None,
			'status': inst.status_tipo,
			'pontos_ultima_calibracao_analisados': pontos_ok,
			'valid_until': valid_until.isoformat() if valid_until else None,
			'ultima_calibracao': last_recebimento.isoformat() if last_recebimento else None,
			'calibration_status': calibration_status,
			'ultimo_certificado': inst.ultimo_certificado_link,
			'periodicidade_calibracao': inst.periodicidade_calibracao,
			'status_obj': {
				'funcionario': inst.status_funcionario,
				'funcionario_id': inst.status_funcionario_id,
				'data_entrega': inst.status_entrega.isoformat() if inst.status_entrega else None,
				'data_devolucao': inst.status_devolucao.isoformat() if inst.status_devolucao else None,
				'data_recebimento': inst.status_recebimento.isoformat() if inst.status_recebimento else None,
				'tipo_status': inst.status_tipo,
			}
		})

	return JsonResponse({
		'instrumentos': items,
		'pending_analysis': {
			'has_pending': pending_analysis_count > 0,
			'count': pending_analysis_count,
		},
		'pagination': {
			'page': page_obj.number,
			'pages': paginator.num_pages,
			'total': paginator.count,
			'has_next': page_obj.has_next(),
			'has_previous': page_obj.has_previous(),
			'per_page': per_page,
		}
	})


@login_required
@require_GET
def indicadores_dashboard(request):
	"""Retorna agregados para cards de indicadores da home.
	Apenas instrumentos com instrumento_controlado=True entram nos cálculos.
	"""

	# ===== INSTRUMENTOS ATIVOS E CONTROLADOS =====
	active_instrumentos = Instrumento.objects.filter(
		status='ativo',
		instrumento_controlado=True
	)

	latest_status_qs = StatusInstrumento.objects.filter(
		instrumento=OuterRef('pk')
	).order_by('-data_entrega')

	last_envio_qs = StatusInstrumento.objects.filter(
		instrumento=OuterRef('pk'),
		tipo_status__istartswith='Enviado ao laboratório'
	).order_by('-data_entrega')

	instrumentos_data = list(
		active_instrumentos.annotate(
			ultimo_status_tipo=Subquery(latest_status_qs.values('tipo_status')[:1]),
			ultimo_status_devolucao=Subquery(latest_status_qs.values('data_devolucao')[:1]),
			ultimo_status_recebimento=Subquery(latest_status_qs.values('data_recebimento')[:1]),
			ultimo_envio_data=Subquery(last_envio_qs.values('data_entrega')[:1]),
		).values(
			'id',
			'ultimo_status_tipo',
			'ultimo_status_devolucao',
			'ultimo_status_recebimento',
			'ultimo_envio_data'
		)
	)

	# ===== CONTADORES DE INSTRUMENTOS =====
	instrumentos_operacao = 0
	instrumentos_calibracao = 0
	instrumento_envio_map = {}

	for inst in instrumentos_data:
		tipo_status = (inst.get('ultimo_status_tipo') or '').lower()
		data_devolucao = inst.get('ultimo_status_devolucao')
		data_recebimento = inst.get('ultimo_status_recebimento')

		if tipo_status.startswith('entregue ao funcionário') and data_devolucao is None:
			instrumentos_operacao += 1

		if tipo_status.startswith('enviado ao laboratório') and data_recebimento is None:
			instrumentos_calibracao += 1

		instrumento_envio_map[inst['id']] = inst.get('ultimo_envio_data')

	# ===== PONTOS DE CALIBRAÇÃO (APENAS DE INSTRUMENTOS CONTROLADOS) =====
	ultima_analise_qs = StatusPontoCalibracao.objects.filter(
		ponto_calibracao=OuterRef('pk')
	).order_by('-data_criacao')

	active_points = PontoCalibracao.objects.filter(
		ativo=True,
		instrumento__status='ativo',
		instrumento__instrumento_controlado=True
	).annotate(
		ultima_analise_data=Subquery(ultima_analise_qs.values('data_criacao')[:1])
	).values('instrumento_id', 'ultima_analise_data')

	pendentes_pontos = 0
	for ponto in active_points:
		last_envio = instrumento_envio_map.get(ponto['instrumento_id'])
		last_analysis = ponto.get('ultima_analise_data')

		if last_envio:
			if not (last_analysis and last_analysis >= last_envio):
				pendentes_pontos += 1
		else:
			if last_analysis is None:
				pendentes_pontos += 1

	return JsonResponse({
		'pontos_pendentes': pendentes_pontos,
		'instrumentos_operacao': instrumentos_operacao,
		'instrumentos_calibracao': instrumentos_calibracao,
	})


@login_required
@require_GET
def instrumentos_disponiveis(request):
	"""Lista instrumentos ativos que não estão entregues a nenhum funcionário."""
	search = (request.GET.get('search') or '').strip()

	open_status = StatusInstrumento.objects.filter(
		instrumento=OuterRef('pk'),
		tipo_status__istartswith='Entregue ao funcionário',
		data_devolucao__isnull=True
	)

	open_posse = FuncionarioInstrumento.objects.filter(
		instrumento=OuterRef('pk'),
		ativo=True,
		data_fim__isnull=True
	)

	qs = (
		Instrumento.objects
		.filter(status='ativo')
		.annotate(
			has_open_status=Exists(open_status),
			has_open_posse=Exists(open_posse)
		)
		.filter(has_open_status=False, has_open_posse=False)
	)

	if search:
		qs = qs.filter(Q(codigo__icontains=search) | Q(descricao__icontains=search))

	try:
		page = int(request.GET.get('page', 1))
	except Exception:
		page = 1

	try:
		per_page = int(request.GET.get('per_page', 50))
	except Exception:
		per_page = 50
	per_page = max(1, min(per_page, 200))

	paginator = Paginator(qs.order_by('codigo'), per_page)
	page_obj = paginator.get_page(page)

	data = [
		{
			'id': inst.id,
			'codigo': inst.codigo,
			'descricao': inst.descricao,
			'tipo': inst.tipo_instrumento.descricao if inst.tipo_instrumento else '',
		}
		for inst in page_obj.object_list
	]

	return JsonResponse({
		'instrumentos': data,
		'pagination': {
			'page': page_obj.number,
			'pages': paginator.num_pages or 1,
			'total': paginator.count,
			'has_next': page_obj.has_next(),
			'has_previous': page_obj.has_previous(),
			'per_page': per_page,
		}
	})


@login_required
@require_GET
def historico_instrumento(request, instrumento_id):
	"""Retorna o histórico de status do instrumento."""
	instrumento = get_object_or_404(Instrumento, pk=instrumento_id)
	status_list = StatusInstrumento.objects.filter(instrumento=instrumento).order_by('-data_entrega')
	historico = []
	for status in status_list:
		data = status.data_entrega
		if status.data_recebimento:
			data = status.data_recebimento
		if status.data_devolucao and (not data or status.data_devolucao > data):
			data = status.data_devolucao
		historico.append({
			'data': data.isoformat() if data else None,
			'descricao': status.tipo_status or ''
		})
	return JsonResponse({'instrumento_id': instrumento.id, 'historico': historico})


@login_required
@require_GET
def ultimo_responsavel_pre_envio(request, instrumento_id):
	"""Retorna o último funcionário responsável antes do envio mais recente ao laboratório."""
	instrumento = get_object_or_404(Instrumento, pk=instrumento_id)
	last_envio = StatusInstrumento.objects.filter(
		instrumento=instrumento,
		tipo_status__istartswith='Enviado ao laboratório'
	).order_by('-data_entrega').first()
	if not last_envio:
		return JsonResponse({'success': True, 'responsavel': None})

	posse_qs = FuncionarioInstrumento.objects.filter(
		instrumento=instrumento,
		funcionario__isnull=False,
		data_fim__isnull=False
	)
	posse = posse_qs.filter(data_fim=last_envio.data_entrega).order_by('-data_inicio').first()
	if not posse:
		posse = posse_qs.filter(data_fim__lte=last_envio.data_entrega).order_by('-data_fim').first()
	if not posse:
		return JsonResponse({'success': True, 'responsavel': None})

	resp_data = {
		'funcionario_id': posse.funcionario.id,
		'funcionario_nome': posse.funcionario.nome,
		'funcionario_matricula': posse.funcionario.matricula,
		'instrumento_id': instrumento.id,
		'instrumento_codigo': instrumento.codigo,
		'instrumento_descricao': instrumento.descricao,
		'data_inicio': posse.data_inicio.isoformat() if posse.data_inicio else None,
		'data_fim': posse.data_fim.isoformat() if posse.data_fim else None,
	}
	return JsonResponse({'success': True, 'responsavel': resp_data})

@login_required
@require_GET
def entregas_api(request):
	"""Retorna lista paginada de entregas com filtros opcionais."""
	entregas = FuncionarioInstrumento.objects.select_related('funcionario', 'instrumento').order_by('-data_inicio')
	status_filter = (request.GET.get('status') or '').strip().lower()
	if status_filter == 'ativo':
		entregas = entregas.filter(ativo=True)
	elif status_filter == 'finalizado':
		entregas = entregas.filter(ativo=False)

	search = (request.GET.get('search') or '').strip()
	if search:
		entregas = entregas.filter(
			Q(funcionario__nome__icontains=search) |
			Q(funcionario__matricula__icontains=search) |
			Q(instrumento__codigo__icontains=search) |
			Q(instrumento__descricao__icontains=search) |
			Q(observacoes__icontains=search)
		)

	try:
		page = int(request.GET.get('page', 1))
	except (TypeError, ValueError):
		page = 1
	try:
		per_page = int(request.GET.get('per_page', 15))
	except (TypeError, ValueError):
		per_page = 15
	per_page = max(1, min(per_page, 200))

	paginator = Paginator(entregas, per_page)
	page_obj = paginator.get_page(page)

	data = []
	for e in page_obj.object_list:
		data.append({
			'id': e.id,
			'funcionario_id': e.funcionario.id if e.funcionario else None,
			'funcionario': e.funcionario.nome if e.funcionario else '',
			'funcionario_matricula': e.funcionario.matricula if e.funcionario else '',
			'instrumento_id': e.instrumento.id if e.instrumento else None,
			'instrumento_codigo': e.instrumento.codigo if e.instrumento else '',
			'instrumento_descricao': e.instrumento.descricao if e.instrumento else '',
			'data_inicio': e.data_inicio.isoformat() if e.data_inicio else None,
			'data_fim': e.data_fim.isoformat() if e.data_fim else None,
			'ativo': e.ativo,
			'observacoes': e.observacoes or '',
		})

	return JsonResponse({
		'entregas': data,
		'pagination': {
			'page': page_obj.number,
			'pages': paginator.num_pages or 1,
			'total': paginator.count,
			'has_next': page_obj.has_next(),
			'has_previous': page_obj.has_previous(),
			'per_page': per_page,
		}
	})


@login_required
@require_http_methods(["POST"])
def import_entregas_csv(request):
	"""Importa entregas históricas via CSV (instrumento x matrícula)."""
	upload = request.FILES.get('file')
	if not upload:
		return JsonResponse({'success': False, 'message': 'Envie um arquivo CSV no campo "file".'}, status=400)

	try:
		raw_bytes = upload.read()
	except Exception:
		return JsonResponse({'success': False, 'message': 'Não foi possível ler o arquivo enviado.'}, status=400)

	if not raw_bytes:
		return JsonResponse({'success': False, 'message': 'O arquivo enviado está vazio.'}, status=400)

	decoded = None
	for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
		try:
			decoded = raw_bytes.decode(encoding)
			break
		except UnicodeDecodeError:
			continue
	if decoded is None:
		return JsonResponse({'success': False, 'message': 'Não foi possível decodificar o arquivo. Utilize UTF-8 ou Latin-1.'}, status=400)

	lines = decoded.splitlines()
	sample_line = next((line for line in lines if line.strip()), '')
	delimiter = _detect_csv_delimiter(sample_line)
	reader = csv.reader(io.StringIO(decoded), delimiter=delimiter)

	header_row = None
	header_line = 0
	for row in reader:
		if not row or not any((cell or '').strip() for cell in row):
			continue
		header_row = row
		header_line = reader.line_num
		break

	if header_row is None:
		return JsonResponse({'success': False, 'message': 'Nenhuma linha válida encontrada no arquivo.'}, status=400)

	normalized_header = [cell.strip().lower() for cell in header_row]
	instrument_aliases = {'instrumento', 'codigo', 'instrumento_codigo', 'codigo_instrumento'}
	matricula_aliases = {'matricula', 'matricula_funcionario', 'funcionario', 'matricula_colaborador'}
	data_aliases = {'data', 'data_inicio', 'data_entrega'}
	obs_aliases = {'observacoes', 'observação', 'obs'}
	has_header = bool(instrument_aliases.intersection(normalized_header) and matricula_aliases.intersection(normalized_header))

	if has_header:
		try:
			instrument_idx = next(idx for idx, name in enumerate(normalized_header) if name in instrument_aliases)
		except StopIteration:
			instrument_idx = None
		try:
			matricula_idx = next(idx for idx, name in enumerate(normalized_header) if name in matricula_aliases)
		except StopIteration:
			matricula_idx = None
		data_idx = next((idx for idx, name in enumerate(normalized_header) if name in data_aliases), None)
		obs_idx = next((idx for idx, name in enumerate(normalized_header) if name in obs_aliases), None)
		if instrument_idx is None or matricula_idx is None:
			return JsonResponse({'success': False, 'message': 'Cabeçalho deve conter as colunas "instrumento" e "matricula".'}, status=400)
	else:
		if len(header_row) < 2:
			return JsonResponse({'success': False, 'message': 'Cada linha deve conter, ao menos, instrumento e matrícula.'}, status=400)
		instrument_idx = 0
		matricula_idx = 1
		data_idx = 2 if len(header_row) > 2 else None
		obs_idx = 3 if len(header_row) > 3 else None

	stats = {'processed': 0, 'success': 0, 'error_rows': 0}
	errors = []
	seen_codes = set()

	def register_row(row, line_number):
		instrument_value = row[instrument_idx].strip() if len(row) > instrument_idx else ''
		matricula_value = row[matricula_idx].strip() if len(row) > matricula_idx else ''
		if not instrument_value or not matricula_value:
			errors.append({'line': line_number, 'error': 'Linha sem instrumento e/ou matrícula.'})
			stats['error_rows'] += 1
			return
		code_key = instrument_value.lower()
		if code_key in seen_codes:
			errors.append({'line': line_number, 'error': 'Instrumento duplicado no arquivo.'})
			stats['error_rows'] += 1
			return
		seen_codes.add(code_key)

		instrumento = Instrumento.objects.filter(codigo__iexact=instrument_value).first()
		if not instrumento:
			errors.append({'line': line_number, 'error': f'Instrumento "{instrument_value}" não encontrado.'})
			stats['error_rows'] += 1
			return
		funcionario = Funcionario.objects.filter(matricula__iexact=matricula_value).first()
		if not funcionario:
			errors.append({'line': line_number, 'error': f'Funcionário com matrícula "{matricula_value}" não encontrado.'})
			stats['error_rows'] += 1
			return

		obs_value = row[obs_idx].strip() if obs_idx is not None and len(row) > obs_idx else ''
		timestamp = None
		if data_idx is not None and len(row) > data_idx:
			timestamp = _parse_csv_datetime(row[data_idx])
		if timestamp is None:
			timestamp = timezone.now()

		try:
			with transaction.atomic():
				FuncionarioInstrumento.objects.filter(instrumento=instrumento, ativo=True).update(ativo=False, data_fim=timestamp)
				StatusInstrumento.objects.filter(instrumento=instrumento, data_devolucao__isnull=True).update(data_devolucao=timestamp)
				posse = FuncionarioInstrumento.objects.create(
					funcionario=funcionario,
					instrumento=instrumento,
					data_inicio=timestamp,
					data_fim=None,
					observacoes=obs_value,
					ativo=True,
				)
				StatusInstrumento.objects.create(
					instrumento=instrumento,
					funcionario=funcionario,
					laboratorio=None,
					data_entrega=timestamp,
					data_devolucao=None,
					data_recebimento=None,
					observacoes=obs_value,
					tipo_status=f'Entregue ao funcionário {funcionario.nome}'
				)
			stats['success'] += 1
		except Exception as exc:
			errors.append({'line': line_number, 'error': f'Falha ao registrar entrega: {str(exc)}'})
			stats['error_rows'] += 1

	if not has_header:
		stats['processed'] += 1
		register_row(header_row, header_line)

	for row in reader:
		if not row or not any((cell or '').strip() for cell in row):
			continue
		stats['processed'] += 1
		register_row(row, reader.line_num)

	summary = f"Importação concluída ({stats['success']} entrega(s) registradas, {stats['error_rows']} linha(s) com erro)."
	return JsonResponse({
		'success': True,
		'message': summary,
		'stats': stats,
		'errors': errors,
	})


@login_required
def list_instrumentos(request):
	instrumentos = Instrumento.objects.select_related('tipo_instrumento').all().order_by('codigo')
	return render(request, 'instrumento/list.html', {'instrumentos': instrumentos})

@login_required
def detail_instrumento(request, pk):
	instrumento = get_object_or_404(Instrumento, pk=pk)
	return render(request, 'instrumento/detail.html', {'instrumento': instrumento})

@login_required
@require_http_methods(["POST"])
def designar_instrumento(request):
	"""API para designar (atribuir) um instrumento a um funcionário.

	Recebe JSON: { funcionário_id, instrumento_id, data_inicio?, data_fim?, observacoes?, assinatura? }
	`assinatura` pode ser uma data URL (data:image/png;base64,...) ou base64 cru.
	"""
	try:
		try:
			data = json.loads(request.body)
		except json.JSONDecodeError:
			body_preview = request.body[:1000].decode('utf-8', errors='replace')
			return JsonResponse({'success': False, 'message': 'JSON inválido no corpo da requisição', 'body_preview': body_preview}, status=400)

		if not data.get('funcionario_id') or not data.get('instrumento_id'):
			return JsonResponse({'success': False, 'message': 'Campos `funcionario_id` e `instrumento_id` são obrigatórios'}, status=400)

		funcionario = get_object_or_404(Funcionario, pk=data.get('funcionario_id'))
		instrumento = get_object_or_404(Instrumento, pk=data.get('instrumento_id'))


		# bloqueia designação se estiver com funcionário ou em laboratório
		open_status = StatusInstrumento.objects.filter(instrumento=instrumento, data_devolucao__isnull=True).order_by('-data_entrega').first()
		if open_status and open_status.tipo_status:
			# enviado ao laboratório e ainda não recebido
			if open_status.tipo_status.startswith('Enviado ao laboratório') and not open_status.data_recebimento:
				return JsonResponse({'success': False, 'message': 'Instrumento indisponível: enviado ao laboratório.'}, status=400)
			# entregue a funcionário e ainda não devolvido
			if open_status.tipo_status.startswith('Entregue ao funcionário') and not open_status.data_devolucao:
				return JsonResponse({'success': False, 'message': 'Instrumento indisponível: já designado para funcionário.'}, status=400)

		data_inicio = data.get('data_inicio') or timezone.now()
		data_fim = data.get('data_fim') or None

		posse = FuncionarioInstrumento.objects.create(
			funcionario=funcionario,
			instrumento=instrumento,
			data_inicio=data_inicio,
			data_fim=data_fim,
			observacoes=data.get('observacoes', ''),
			ativo=True,
		)

		# fechar status anteriores abertos (sem data_devolucao)
		try:
			StatusInstrumento.objects.filter(instrumento=instrumento, data_devolucao__isnull=True).update(data_devolucao=data_inicio)
		except Exception:
			pass

		# criar novo status indicando que instrumento foi entregue
		try:
			StatusInstrumento.objects.create(
				instrumento=instrumento,
				funcionario=funcionario,
				laboratorio=None,
				data_entrega=data_inicio,
				data_devolucao=None,
				observacoes=data.get('observacoes', ''),
				tipo_status=f'Entregue ao funcionário {funcionario.nome}'
			)
		except Exception:
			pass

		# opcional: salvar assinatura enviada em base64
		assinatura_b64 = data.get('assinatura')
		if assinatura_b64:
			if isinstance(assinatura_b64, str) and assinatura_b64.startswith('data:'):
				header, b64 = assinatura_b64.split(',', 1)
				try:
					ext = header.split('/')[1].split(';')[0]
				except Exception:
					ext = 'png'
			else:
				b64 = assinatura_b64
				ext = 'png'

			try:
				file_data = base64.b64decode(b64)
				filename = f'assinatura_posse_{posse.id}.{ext}'
				assinatura = AssinaturaFuncionarioInstrumento(posse=posse)
				assinatura.imagem.save(filename, ContentFile(file_data))
				assinatura.save()
			except Exception:
				# não bloquear criação da posse por falha na assinatura
				pass

		return JsonResponse({'success': True, 'message': 'Instrumento designado com sucesso', 'posse_id': posse.id})
	except Exception as e:
		return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def devolver_instrumento(request):
	"""Registra a devolução de um instrumento por um funcionário."""
	try:
		try:
			data = json.loads(request.body)
		except json.JSONDecodeError:
			body_preview = request.body[:1000].decode('utf-8', errors='replace')
			return JsonResponse({'success': False, 'message': 'JSON inválido no corpo da requisição', 'body_preview': body_preview}, status=400)

		funcionario_id = data.get('funcionario_id')
		instrumento_id = data.get('instrumento_id')
		if not funcionario_id or not instrumento_id:
			return JsonResponse({'success': False, 'message': 'Campos `funcionario_id` e `instrumento_id` são obrigatórios'}, status=400)

		funcionario = get_object_or_404(Funcionario, pk=funcionario_id)
		instrumento = get_object_or_404(Instrumento, pk=instrumento_id)

		data_devolucao_raw = data.get('data_devolucao') or data.get('data_fim')
		if data_devolucao_raw:
			try:
				devolucao_dt = parse_datetime(data_devolucao_raw)
			except Exception:
				devolucao_dt = None
			if not devolucao_dt:
				devolucao_dt = timezone.now()
		else:
			devolucao_dt = timezone.now()

		posse = FuncionarioInstrumento.objects.filter(
			funcionario=funcionario,
			instrumento=instrumento,
			ativo=True
		).order_by('-data_inicio').first()
		if not posse:
			posse = FuncionarioInstrumento.objects.filter(instrumento=instrumento, ativo=True).order_by('-data_inicio').first()
		if not posse:
			return JsonResponse({'success': False, 'message': 'Nenhuma posse ativa encontrada para este instrumento'}, status=400)
		if posse.funcionario_id != funcionario.id:
			return JsonResponse({'success': False, 'message': 'Instrumento não está vinculado ao funcionário informado'}, status=400)

		observacoes = (data.get('observacoes') or '').strip()
		posse.data_fim = devolucao_dt
		posse.ativo = False
		if observacoes:
			posse.observacoes = f"{posse.observacoes}\nDevolução: {observacoes}" if posse.observacoes else f"Devolução: {observacoes}"
		posse.save()

		StatusInstrumento.objects.filter(
			instrumento=instrumento,
			tipo_status__istartswith='Entregue ao funcionário',
			data_devolucao__isnull=True
		).update(data_devolucao=devolucao_dt)

		status = StatusInstrumento.objects.create(
			instrumento=instrumento,
			funcionario=funcionario,
			laboratorio=None,
			data_entrega=devolucao_dt,
			data_devolucao=devolucao_dt,
			data_recebimento=None,
			observacoes=observacoes,
			tipo_status=f'Devolvido pelo funcionário {funcionario.nome}'
		)

		return JsonResponse({'success': True, 'message': 'Devolução registrada com sucesso', 'posse_id': posse.id, 'status_id': status.id})
	except Exception as e:
		return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def enviar_para_calibracao(request):
	"""Marca instrumento como enviado ao laboratório.

	Recebe JSON: { instrumento_id, laboratorio_id? , laboratorio_nome? , observacoes? }

	AÃ§Ã£o:
	- fecha quaisquer status abertos (data_devolucao is null) preenchendo com data atual
	- fecha posses ativas (FuncionarioInstrumento) definindo data_fim
	- cria novo StatusInstrumento com tipo_status 'Enviado ao laboratório X' e data_entrega agora
	"""
	try:
		try:
			data = json.loads(request.body)
		except json.JSONDecodeError:
			return JsonResponse({'success': False, 'message': 'JSON invÃ¡lido'}, status=400)

		instrumento_id = data.get('instrumento_id')
		if not instrumento_id:
			return JsonResponse({'success': False, 'message': 'instrumento_id obrigatório'}, status=400)

		instrumento = get_object_or_404(Instrumento, pk=instrumento_id)

		lab_name = None
		laboratorio_obj = None
		if data.get('laboratorio_id'):
			try:
				laboratorio_obj = Laboratorio.objects.get(pk=int(data.get('laboratorio_id')))
				lab_name = laboratorio_obj.nome
			except Exception:
				laboratorio_obj = None
		if not lab_name and data.get('laboratorio_nome'):
			lab_name = str(data.get('laboratorio_nome')).strip()
		if not lab_name:
			lab_name = 'externo'

		# allow client-specified send datetime (ISO 8601) via 'data_entrega'
		data_entrega_raw = data.get('data_entrega') or data.get('dataEnv') or data.get('data_envio')
		if data_entrega_raw:
			try:
				parsed = parse_datetime(data_entrega_raw)
			except Exception:
				parsed = None
			now = parsed or timezone.now()
		else:
			now = timezone.now()

		# fechar status anteriores abertos (sem data_devolucao)
		try:
			StatusInstrumento.objects.filter(instrumento=instrumento, data_devolucao__isnull=True).update(data_devolucao=now)
		except Exception:
			pass

		# fechar posses ativas
		try:
			FuncionarioInstrumento.objects.filter(instrumento=instrumento, data_fim__isnull=True).update(data_fim=now, ativo=False)
		except Exception:
			pass

		# marcar data_recebimento no Ãºltimo status que ainda nÃ£o tem
		try:
			last_without_receb = StatusInstrumento.objects.filter(instrumento=instrumento, data_recebimento__isnull=True).order_by('-data_entrega').first()
			if last_without_receb:
				last_without_receb.data_recebimento = now
				last_without_receb.save()
		except Exception:
			pass

		# criar novo status indicando envio ao laboratÃ³rio
		try:
			StatusInstrumento.objects.create(
				instrumento=instrumento,
				funcionario=None,
				laboratorio=None,
				data_entrega=now,
				data_devolucao=None,
				data_recebimento=None,
				observacoes=data.get('observacoes', ''),
				tipo_status=f'Enviado ao laboratório {lab_name}'
			)
		except Exception as e:
			return JsonResponse({'success': False, 'message': f'Erro ao criar status: {str(e)}'}, status=500)

		return JsonResponse({'success': True, 'message': f'Instrumento enviado ao laboratório {lab_name}'})
	except Exception as e:
		return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def receber_da_calibracao(request):
	"""Recebe instrumento da calibraÃ§Ã£o e anexa certificado.

	Espera JSON: {
		instrumento_id: int,
		laboratorio_id?: int,
		laboratorio_nome?: str,
		link: str,
		observacoes?: str,
		data_recebimento?: ISO datetime
	}

	Ações:
	- localiza instrumento
	- atualiza último status 'Enviado ao laboratório X' sem data_devolucao preenchendo data_devolucao/data_recebimento se aplicável
	- cria novo StatusInstrumento tipo 'Recebido do laboratório X'
	- cria CertificadoCalibracao vinculado ao status de recebimento com os dados enviados
	"""
	try:
		try:
			data = json.loads(request.body)
		except json.JSONDecodeError:
			return JsonResponse({'success': False, 'message': 'JSON invÃ¡lido'}, status=400)

		instrumento_id = data.get('instrumento_id')
		if not instrumento_id:
			return JsonResponse({'success': False, 'message': 'instrumento_id obrigatÃ³rio'}, status=400)

		instrumento = get_object_or_404(Instrumento, pk=instrumento_id)

		# resolve laboratório nome, priorizando parâmetros e caindo para último envio
		lab_name = None
		laboratorio_obj = None
		if data.get('laboratorio_id'):
			try:
				laboratorio_obj = Laboratorio.objects.get(pk=int(data.get('laboratorio_id')))
				lab_name = laboratorio_obj.nome
			except Exception:
				laboratorio_obj = None
		if not lab_name and data.get('laboratorio_nome'):
			lab_name = str(data.get('laboratorio_nome')).strip()

		last_sent_for_name = StatusInstrumento.objects.filter(
			instrumento=instrumento,
			tipo_status__startswith='Enviado ao laboratório'
		).order_by('-data_entrega').first()
		if not lab_name and last_sent_for_name and last_sent_for_name.tipo_status:
			marker = 'Enviado ao laboratório'
			status_text = last_sent_for_name.tipo_status.strip()
			if status_text.lower().startswith(marker.lower()):
				lab_name = status_text[len(marker):].strip()

		if not lab_name:
			lab_name = 'externo'

		# parse data_recebimento ou usa agora (mantém duas referências de tempo)
		data_receb_raw = data.get('data_recebimento') or data.get('data_receb') or data.get('data')
		if data_receb_raw:
			try:
				parsed = parse_datetime(data_receb_raw)
			except Exception:
				parsed = None
			recebimento_dt = parsed or timezone.now()
		else:
			recebimento_dt = timezone.now()
		registro_dt = timezone.now()

		# marcar data_recebimento/data_devolucao no Ãºltimo status de envio que estiver sem recebimento
		try:
			last_sent = StatusInstrumento.objects.filter(instrumento=instrumento, tipo_status__startswith='Enviado ao laborat', data_recebimento__isnull=True).order_by('-data_entrega').first()
			if last_sent:
				last_sent.data_recebimento = recebimento_dt
				last_sent.data_devolucao = recebimento_dt
				last_sent.save()
		except Exception:
			pass

		# determinar funcionário que está recebendo (usuário logado -> Funcionario)
		receiver_funcionario = None
		try:
			user = request.user
			if user and user.is_authenticated:
				# tentar por matrícula (username), senão por email
				receiver_funcionario = Funcionario.objects.filter(matricula=str(user.username)).first()
				if not receiver_funcionario and getattr(user, 'email', None):
					receiver_funcionario = Funcionario.objects.filter(email__iexact=user.email).first()
		except Exception:
			receiver_funcionario = None

		# criar novo status indicando recebimento do laboratório
		try:
			recv_status = StatusInstrumento.objects.create(
				instrumento=instrumento,
				funcionario=receiver_funcionario,
				laboratorio=laboratorio_obj if laboratorio_obj else None,
				data_entrega=registro_dt,
				data_devolucao=None,
				data_recebimento=recebimento_dt,
				observacoes=data.get('observacoes', ''),
				tipo_status=f'Recebido do laboratório {lab_name}'
			)
		except Exception as e:
			return JsonResponse({'success': False, 'message': f'Erro ao criar status de recebimento: {str(e)}'}, status=500)

		# criar certificado vinculado
		try:
			link = data.get('link')
			if not link:
				return JsonResponse({'success': False, 'message': 'Campo `link` do certificado Ã© obrigatÃ³rio'}, status=400)

			cert = CertificadoCalibracao.objects.create(
				status=recv_status,
				link=link,
			)
		except Exception as e:
			return JsonResponse({'success': False, 'message': f'Erro ao criar certificado: {str(e)}'}, status=500)

		return JsonResponse({'success': True, 'message': 'Instrumento recebido e certificado anexado', 'certificado_id': cert.id, 'status_id': recv_status.id})
	except Exception as e:
		return JsonResponse({'success': False, 'message': str(e)}, status=400)

@login_required
@require_http_methods(["POST"])
def registrar_status_ponto(request):
	"""Registra o status/anÃ¡lise de um PontoCalibracao.

	Espera JSON: {
		ponto_id: int,
		incerteza?: number,
		tendencia?: str,
		resultado?: 'aprovado'|'reprovado'|'condicional',
		observacoes?: str
	}

	Ações:
	- encontra o `PontoCalibracao`
	- localiza o último `CertificadoCalibracao` do instrumento relacionado
	- cria `StatusPontoCalibracao` vinculado a esse certificado e ao usuário logado (quando possível)
	"""
	try:
		try:
			data = json.loads(request.body)
		except json.JSONDecodeError:
			return JsonResponse({'success': False, 'message': 'JSON invÃ¡lido'}, status=400)

		ponto_id = data.get('ponto_id') or data.get('ponto')
		if not ponto_id:
			return JsonResponse({'success': False, 'message': 'ponto_id Ã© obrigatÃ³rio'}, status=400)

		ponto = get_object_or_404(PontoCalibracao, pk=ponto_id)
		instrumento = ponto.instrumento

		# localizar Ãºltimo certificado do instrumento (opcional)
		last_cert = CertificadoCalibracao.objects.filter(status__instrumento=instrumento).order_by('-data_criacao').first()

		# determinar responsavel pela analise (usuÃ¡rio logado -> Funcionario)
		responsavel = None
		try:
			user = request.user
			if user and user.is_authenticated:
				responsavel = Funcionario.objects.filter(matricula=str(user.username)).first()
				if not responsavel and getattr(user, 'email', None):
					responsavel = Funcionario.objects.filter(email__iexact=user.email).first()
		except Exception:
			responsavel = None

		# mapear campos
		incerteza = data.get('incerteza') or data.get('inincerteza')
		if incerteza is not None:
			try:
				from decimal import Decimal
				incerteza = Decimal(str(incerteza))
			except Exception:
				incerteza = None

		tendencia = data.get('tendencia', '')
		resultado = data.get('resultado')
		observacoes = data.get('observacoes', '')

		status_kwargs = {
			'ponto_calibracao': ponto,
			'incerteza': incerteza,
			'tendencia': tendencia,
			'resultado': resultado,
			'observacoes': observacoes,
			'responsavel': responsavel,
		}
		if last_cert:
			status_kwargs['certificado'] = last_cert

		status_ponto = StatusPontoCalibracao.objects.create(**status_kwargs)

		return JsonResponse({'success': True, 'message': 'Status do ponto registrado', 'status_ponto_id': status_ponto.id})
	except Exception as e:
		return JsonResponse({'success': False, 'message': str(e)}, status=400)

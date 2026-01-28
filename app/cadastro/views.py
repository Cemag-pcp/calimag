from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, OuterRef, Subquery
from django.core.exceptions import ValidationError
from .models import Instrumento, Funcionario, PontoCalibracao, TipoInstrumento, Setor
import csv
import io
import json


def _detect_delimiter(sample_line):
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


@login_required
def instrumentos_list(request):
    """View principal para listagem de instrumentos"""
    return render(request, 'cadastro/instrumentos.html')

@login_required
@require_http_methods(["GET"])
def instrumentos_api(request):
    """API para listar instrumentos com paginação e busca"""
    search = request.GET.get('search', '')
    codigo = request.GET.get('codigo')
    status = request.GET.get('status')
    tipo_id = request.GET.get('tipo_id')
    controlado = request.GET.get('controlado')
    try:
        page = int(request.GET.get('page', 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.GET.get('per_page', 10))
    except (TypeError, ValueError):
        per_page = 10

    instrumentos = Instrumento.objects.select_related('tipo_instrumento').all()

    if search:
        instrumentos = instrumentos.filter(
            Q(codigo__icontains=search) |
            Q(descricao__icontains=search) |
            Q(fabricante__icontains=search) |
            Q(modelo__icontains=search)
        )

    if codigo:
        instrumentos = instrumentos.filter(codigo__icontains=codigo)

    if status:
        status_keys = {choice[0] for choice in Instrumento.STATUS_CHOICES}
        if status in status_keys:
            instrumentos = instrumentos.filter(status=status)

    if tipo_id:
        instrumentos = instrumentos.filter(tipo_instrumento_id=tipo_id)

    if controlado:
        normalized = controlado.lower()
        if normalized in {'1', 'true', 't', 'sim'}:
            instrumentos = instrumentos.filter(instrumento_controlado=True)
        elif normalized in {'0', 'false', 'f', 'nao', 'não'}:
            instrumentos = instrumentos.filter(instrumento_controlado=False)

    instrumentos = instrumentos.order_by('-data_cadastro')

    paginator = Paginator(instrumentos, per_page)
    page_obj = paginator.get_page(page)

    instrumentos_list = []
    for i in page_obj:
        instrumentos_list.append({
            'id': i.id,
            'codigo': i.codigo,
            'descricao': i.descricao,
            'tipo': i.tipo_instrumento.descricao if i.tipo_instrumento else '',
            'tipo_value': i.tipo_instrumento.id if i.tipo_instrumento else None,
            'fabricante': i.fabricante,
            'modelo': i.modelo,
            'controlado': getattr(i, 'instrumento_controlado', False),
            'status': i.get_status_display() if hasattr(i, 'get_status_display') else '',
            'status_value': getattr(i, 'status', None),
            'observacoes': i.observacoes,
            'total_pontos': getattr(i, 'total_pontos_calibracao', None),
            'data_aquisicao': i.data_aquisicao.strftime('%Y-%m-%d') if getattr(i, 'data_aquisicao', None) else '',
            'periodicidade': i.periodicidade_calibracao,
        })

    data = {
        'instrumentos': instrumentos_list,
        'pagination': {
            'page': page_obj.number,
            'pages': paginator.num_pages,
            'total': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }
    }

    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def instrumento_create(request):
    """API para criar novo instrumento"""
    try:
        data = json.loads(request.body)

        tipo_instrumento = None
        if data.get('tipo_instrumento_id'):
            tipo_instrumento = TipoInstrumento.objects.get(id=data['tipo_instrumento_id'])

        instrumento = Instrumento.objects.create(
            codigo=data.get('codigo', ''),
            descricao=data.get('descricao', ''),
            fabricante=data.get('fabricante', ''),
            modelo=data.get('modelo', ''),
            tipo_instrumento=tipo_instrumento,
            instrumento_controlado=data.get('instrumento_controlado', False),
            status=data.get('status', getattr(Instrumento, 'STATUS_DEFAULT', 'ativo')),
            observacoes=data.get('observacoes', ''),
            data_aquisicao=data.get('data_aquisicao') or None,
        )

        return JsonResponse({
            'success': True,
            'message': 'Instrumento cadastrado com sucesso!',
            'instrumento': {
                'id': instrumento.id,
                'codigo': instrumento.codigo,
                'descricao': instrumento.descricao,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao cadastrar instrumento: {str(e)}'
        }, status=400)


@login_required
@require_http_methods(["GET"])
def tipos_instrumento_api(request):
    """API para listar tipos de instrumento ativos"""
    try:
        tipos = TipoInstrumento.objects.filter(ativo=True).order_by('descricao')
        data = {
            'tipos': [
                {'id': t.id, 'descricao': t.descricao, 'documento_qualidade': t.documento_qualidade}
                for t in tipos
            ]
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
def tipos_instrumento_list(request):
    """View para gerenciamento de tipos de instrumento"""
    return render(request, 'cadastro/tipos_instrumento.html')


@login_required
@require_http_methods(["POST"])
def tipos_instrumento_create(request):
    try:
        data = json.loads(request.body)
        tipo = TipoInstrumento.objects.create(
            descricao=data.get('descricao', '').strip(),
            ativo=data.get('ativo', True),
            documento_qualidade=data.get('documento_qualidade', '').strip()
        )
        return JsonResponse({'success': True, 'message': 'Tipo criado', 'tipo': {'id': tipo.id, 'descricao': tipo.descricao}})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["PUT"])
def tipos_instrumento_update(request, pk):
    try:
        tipo = get_object_or_404(TipoInstrumento, pk=pk)
        data = json.loads(request.body)
        tipo.descricao = data.get('descricao', tipo.descricao).strip()
        tipo.ativo = data.get('ativo', tipo.ativo)
        tipo.documento_qualidade = data.get('documento_qualidade', tipo.documento_qualidade).strip()
        tipo.save()
        return JsonResponse({'success': True, 'message': 'Tipo atualizado'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def tipos_instrumento_delete(request, pk):
    try:
        tipo = get_object_or_404(TipoInstrumento, pk=pk)
        tipo.delete()
        return JsonResponse({'success': True, 'message': 'Tipo deletado'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ================================
# LABORATÓRIOS
# ================================


@login_required
@require_http_methods(["GET"])
def laboratorios_api(request):
    """API para listar laboratórios ativos"""
    try:
        from .models import Laboratorio
        labs = Laboratorio.objects.filter(ativo=True).order_by('nome')
        data = {
            'laboratorios': [
                {'id': l.id, 'nome': l.nome}
                for l in labs
            ]
        }
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["GET"])
def setores_api(request):
    """API para listar setores ativos"""
    try:
        setores = Setor.objects.filter(ativo=True).order_by('nome')
        data = {'setores': [{'id': s.id, 'nome': s.nome} for s in setores]}
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
def setores_list(request):
    """View para gerenciamento de setores"""
    return render(request, 'cadastro/setores.html')


@login_required
@require_http_methods(["POST"])
def setores_create(request):
    try:
        data = json.loads(request.body)
        setor = Setor.objects.create(
            nome=data.get('nome', '').strip(),
            descricao=data.get('descricao', '').strip(),
            ativo=data.get('ativo', True)
        )
        return JsonResponse({'success': True, 'message': 'Setor criado', 'setor': {'id': setor.id, 'nome': setor.nome}})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["PUT"])
def setores_update(request, pk):
    try:
        setor = get_object_or_404(Setor, pk=pk)
        data = json.loads(request.body)
        setor.nome = data.get('nome', setor.nome).strip()
        setor.descricao = data.get('descricao', setor.descricao)
        setor.ativo = data.get('ativo', setor.ativo)
        setor.save()
        return JsonResponse({'success': True, 'message': 'Setor atualizado'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def setores_delete(request, pk):
    try:
        setor = get_object_or_404(Setor, pk=pk)
        nome = setor.nome
        setor.delete()
        return JsonResponse({'success': True, 'message': f'Setor {nome} deletado com sucesso!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
def laboratorios_list(request):
    """View para gerenciamento de laboratórios"""
    return render(request, 'cadastro/laboratorios.html')


@login_required
@require_http_methods(["POST"])
def laboratorios_create(request):
    try:
        data = json.loads(request.body)
        from .models import Laboratorio
        lab = Laboratorio.objects.create(
            nome=data.get('nome', '').strip(),
            ativo=data.get('ativo', True)
        )
        return JsonResponse({'success': True, 'message': 'Laboratório criado', 'laboratorio': {'id': lab.id, 'nome': lab.nome}})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["PUT"])
def laboratorios_update(request, pk):
    try:
        from .models import Laboratorio
        lab = get_object_or_404(Laboratorio, pk=pk)
        data = json.loads(request.body)
        lab.nome = data.get('nome', lab.nome).strip()
        lab.ativo = data.get('ativo', lab.ativo)
        lab.save()
        return JsonResponse({'success': True, 'message': 'Laboratório atualizado'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def laboratorios_delete(request, pk):
    try:
        from .models import Laboratorio
        lab = get_object_or_404(Laboratorio, pk=pk)
        nome = lab.nome
        lab.delete()
        return JsonResponse({'success': True, 'message': f'Laboratório {nome} deletado com sucesso!'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["PUT"])
def instrumento_update(request, pk):
    """API para atualizar instrumento"""
    try:
        instrumento = get_object_or_404(Instrumento, pk=pk)
        data = json.loads(request.body)
        
        instrumento.codigo = data.get('codigo', instrumento.codigo)
        instrumento.descricao = data.get('descricao', instrumento.descricao)
        # update tipo if provided (expecting tipo_instrumento_id)
        if data.get('tipo_instrumento_id'):
            try:
                instrumento.tipo_instrumento = TipoInstrumento.objects.get(id=data['tipo_instrumento_id'])
            except TipoInstrumento.DoesNotExist:
                instrumento.tipo_instrumento = None
        instrumento.fabricante = data.get('fabricante', instrumento.fabricante)
        instrumento.periodicidade_calibracao = data.get('periodicidade', instrumento.periodicidade_calibracao)
        instrumento.modelo = data.get('modelo', instrumento.modelo)
        instrumento.instrumento_controlado = data.get('instrumento_controlado', instrumento.instrumento_controlado)
        instrumento.observacoes = data.get('observacoes', instrumento.observacoes)
        status_value = data.get('status')
        if status_value:
            valid_status = {choice[0] for choice in Instrumento.STATUS_CHOICES}
            if status_value in valid_status:
                instrumento.status = status_value
        
        if data.get('data_aquisicao'):
            instrumento.data_aquisicao = data['data_aquisicao']
        
        if data.get('responsavel_id'):
            instrumento.responsavel = Funcionario.objects.get(id=data['responsavel_id'])
        else:
            instrumento.responsavel = None
        instrumento.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Instrumento atualizado com sucesso!'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao atualizar instrumento: {str(e)}'
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def instrumento_delete(request, pk):
    """API para deletar instrumento"""
    try:
        instrumento = get_object_or_404(Instrumento, pk=pk)
        codigo = instrumento.codigo
        instrumento.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Instrumento {codigo} deletado com sucesso!'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao deletar instrumento: {str(e)}'
        }, status=400)


@login_required
@require_http_methods(["GET"])
def funcionarios_api(request):
    """API para listar funcionários ativos"""
    funcionarios = Funcionario.objects.filter(ativo=True).order_by('nome')
    
    data = {
        'funcionarios': [
            {
                'id': f.id,
                'matricula': f.matricula,
                'nome': f.nome,
                'cargo': f.cargo,
            }
            for f in funcionarios
        ]
    }
    
    return JsonResponse(data)


@login_required
def funcionarios_list(request):
    """View para listagem/gerenciamento de funcionários"""
    return render(request, 'cadastro/funcionarios.html')


@login_required
@require_http_methods(["GET"])
def funcionarios_lista_api(request):
    """API para listar funcionários com paginação e busca"""
    search = request.GET.get('search', '')
    page = request.GET.get('page', 1)
    per_page = request.GET.get('per_page', 10)
    
    funcionarios = Funcionario.objects.all()
    if search:
        funcionarios = funcionarios.filter(
            Q(matricula__icontains=search) |
            Q(nome__icontains=search) |
            Q(cargo__icontains=search) |
            Q(setor__nome__icontains=search)
        )

    funcionarios = funcionarios.order_by('-data_cadastro')
    paginator = Paginator(funcionarios, per_page)
    page_obj = paginator.get_page(page)

    data = {
        'funcionarios': [
            {
                'id': f.id,
                'matricula': f.matricula,
                'nome': f.nome,
                'email': f.email,
                'cargo': f.cargo,
                'setor': f.setor.nome if getattr(f, 'setor', None) else '',
                'setor_id': f.setor.id if getattr(f, 'setor', None) else None,
                'telefone': f.telefone,
                'ativo': f.ativo,
                'data_admissao': f.data_admissao.isoformat() if f.data_admissao else None,
            }
            for f in page_obj.object_list
        ],
        'pagination': {
            'page': page_obj.number,
            'pages': paginator.num_pages,
            'total': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        }
    }

    return JsonResponse(data)


@login_required
@require_http_methods(["POST"])
def funcionarios_import(request):
    """Importa funcionários via arquivo CSV contendo matrícula e nome."""
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

    sample_line = ''
    for line in decoded.splitlines():
        if line.strip():
            sample_line = line
            break
    delimiter = _detect_delimiter(sample_line)
    stream = io.StringIO(decoded)
    reader = csv.reader(stream, delimiter=delimiter)

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
    has_header = 'matricula' in normalized_header and 'nome' in normalized_header

    if has_header:
        idx_matricula = normalized_header.index('matricula')
        idx_nome = normalized_header.index('nome')
    else:
        if len(header_row) < 2:
            return JsonResponse({'success': False, 'message': 'Cada linha deve conter, ao menos, matrícula e nome.'}, status=400)
        idx_matricula = 0
        idx_nome = 1

    stats = {'processed': 0, 'created': 0, 'updated': 0, 'unchanged': 0, 'error_rows': 0}
    errors = []
    seen_in_file = set()

    def process_row(row, line_number):
        matricula = row[idx_matricula].strip() if len(row) > idx_matricula else ''
        nome = row[idx_nome].strip() if len(row) > idx_nome else ''
        if not matricula or not nome:
            errors.append({'line': line_number, 'error': 'Linha sem matrícula e/ou nome.'})
            stats['error_rows'] += 1
            return
        key = matricula.lower()
        if key in seen_in_file:
            errors.append({'line': line_number, 'error': 'Matrícula duplicada no arquivo.'})
            stats['error_rows'] += 1
            return
        seen_in_file.add(key)

        stats['processed'] += 1
        funcionario, created = Funcionario.objects.get_or_create(
            matricula=matricula,
            defaults={'nome': nome, 'ativo': True}
        )
        if created:
            stats['created'] += 1
            return

        if funcionario.nome != nome:
            funcionario.nome = nome
            funcionario.save(update_fields=['nome'])
            stats['updated'] += 1
        else:
            stats['unchanged'] += 1

    if not has_header:
        process_row(header_row, header_line)

    for row in reader:
        if not row or not any((cell or '').strip() for cell in row):
            continue
        process_row(row, reader.line_num)

    message_bits = [
        f"Carga processada ({stats['processed']} linha(s) válidas)",
        f"{stats['created']} novo(s)",
        f"{stats['updated']} atualizado(s)"
    ]
    if stats['error_rows']:
        message_bits.append(f"{stats['error_rows']} linha(s) ignoradas")

    return JsonResponse({
        'success': True,
        'message': ', '.join(message_bits) + '.',
        'stats': stats,
        'errors': errors,
    })


@login_required
@require_http_methods(["POST"])
def funcionario_create(request):
    """API para criar novo funcionário"""
    try:
        data = json.loads(request.body)
        # resolve setor input (id)
        setor_obj = None
        setor_input = data.get('setor')
        if setor_input:
            try:
                setor_obj = Setor.objects.get(pk=int(setor_input))
            except Exception:
                setor_obj = None

        funcionario = Funcionario.objects.create(
            matricula=data['matricula'],
            nome=data['nome'],
            email=data.get('email', ''),
            cargo=data.get('cargo', ''),
            telefone=data.get('telefone', ''),
            ativo=data.get('ativo', True),
            data_admissao=data.get('data_admissao') or None,
        )

        return JsonResponse({
            'success': True,
            'message': 'Funcionário cadastrado com sucesso!',
            'funcionario': {
                'id': funcionario.id,
                'matricula': funcionario.matricula,
                'nome': funcionario.nome,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao cadastrar funcionário: {str(e)}'
        }, status=400)


@login_required
@require_http_methods(["PUT"])
def funcionario_update(request, pk):
    """API para atualizar funcionário"""
    try:
        funcionario = get_object_or_404(Funcionario, pk=pk)
        data = json.loads(request.body)

        funcionario.matricula = data.get('matricula', funcionario.matricula)
        funcionario.nome = data.get('nome', funcionario.nome)
        funcionario.email = data.get('email', funcionario.email)
        funcionario.cargo = data.get('cargo', funcionario.cargo)
        # resolve setor input (id)
        setor_input = data.get('setor')
        if setor_input is not None:
            if setor_input == '' or setor_input is False:
                funcionario.setor = None
            else:
                try:
                    funcionario.setor = Setor.objects.get(pk=int(setor_input))
                except Exception:
                    funcionario.setor = None
        funcionario.telefone = data.get('telefone', funcionario.telefone)
        funcionario.ativo = data.get('ativo', funcionario.ativo)

        if data.get('data_admissao'):
            funcionario.data_admissao = data['data_admissao']

        funcionario.save()

        return JsonResponse({
            'success': True,
            'message': 'Funcionário atualizado com sucesso!'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao atualizar funcionário: {str(e)}'
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def funcionario_delete(request, pk):
    """API para deletar funcionário"""
    try:
        funcionario = get_object_or_404(Funcionario, pk=pk)
        matricula = funcionario.matricula
        funcionario.delete()
        return JsonResponse({
            'success': True,
            'message': f'Funcionário {matricula} deletado com sucesso!'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao deletar funcionário: {str(e)}'
        }, status=400)


# ============================================
# PONTOS DE CALIBRAÇÃO
# ============================================

@login_required
@require_http_methods(["GET"])
def pontos_calibracao_api(request, instrumento_id):
    """API para listar pontos de calibração de um instrumento"""
    try:
        instrumento = get_object_or_404(Instrumento, pk=instrumento_id)
        # Anotar cada ponto com os campos da última análise (se houver)
        from app.instrumento.models import StatusPontoCalibracao
        latest_status = StatusPontoCalibracao.objects.filter(ponto_calibracao=OuterRef('pk')).order_by('-data_criacao')

        pontos = PontoCalibracao.objects.filter(
            instrumento=instrumento,
        ).annotate(
            ultima_data_analise=Subquery(latest_status.values('data_criacao')[:1]),
            ultima_incerteza=Subquery(latest_status.values('incerteza')[:1]),
            ultima_tendencia=Subquery(latest_status.values('tendencia')[:1]),
            ultima_resultado=Subquery(latest_status.values('resultado')[:1]),
        ).order_by('sequencia')
        
        data = {
            'pontos': [
                {
                    'id': p.id,
                    'sequencia': p.sequencia,
                    'descricao': p.descricao,
                    'valor_nominal': f"{str(p.valor_maximo)} - {str(p.valor_minimo)}",
                    'valor_nominal_maximo':p.valor_maximo,
                    'valor_nominal_minimo':p.valor_minimo,
                    'unidade': p.unidade,
                    'unidade_display': p.get_unidade_display(),
                    'tolerancia_mais': str(p.tolerancia_mais) if p.tolerancia_mais else '',
                    'tolerancia_menos': str(p.tolerancia_menos) if p.tolerancia_menos else '',
                    'observacoes': p.observacoes,
                    'ativo': p.ativo,
                    'ultima_data_analise': p.ultima_data_analise.isoformat() if getattr(p, 'ultima_data_analise', None) else None,
                    'ultima_incerteza': str(p.ultima_incerteza) if getattr(p, 'ultima_incerteza', None) is not None else None,
                    'ultima_tendencia': p.ultima_tendencia or '',
                    'ultima_resultado': p.ultima_resultado or None,
                }
                for p in pontos
            ]
        }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao carregar pontos: {str(e)}'
        }, status=400)

@login_required
@require_http_methods(["GET"])
def pontos_calibracao_api_only_ativo(request, instrumento_id):
    """API para listar pontos de calibração de um instrumento"""
    try:
        instrumento = get_object_or_404(Instrumento, pk=instrumento_id)
        # Anotar cada ponto com os campos da última análise (se houver)
        from app.instrumento.models import StatusPontoCalibracao
        latest_status = StatusPontoCalibracao.objects.filter(ponto_calibracao=OuterRef('pk')).order_by('-data_criacao')

        pontos = PontoCalibracao.objects.filter(
            instrumento=instrumento,
            ativo=True,
        ).annotate(
            ultima_data_analise=Subquery(latest_status.values('data_criacao')[:1]),
            ultima_incerteza=Subquery(latest_status.values('incerteza')[:1]),
            ultima_tendencia=Subquery(latest_status.values('tendencia')[:1]),
            ultima_resultado=Subquery(latest_status.values('resultado')[:1]),
        ).order_by('sequencia')
        
        data = {
            'pontos': [
                {
                    'id': p.id,
                    'sequencia': p.sequencia,
                    'descricao': p.descricao,
                    'valor_nominal_minimo': p.valor_minimo,
                    'valor_nominal_maximo': p.valor_maximo,
                    'valor_nominal': f"{str(p.valor_maximo)} - {str(p.valor_minimo)}",
                    'unidade': p.unidade,
                    'unidade_display': p.get_unidade_display(),
                    'tolerancia_mais': str(p.tolerancia_mais) if p.tolerancia_mais else '',
                    'tolerancia_menos': str(p.tolerancia_menos) if p.tolerancia_menos else '',
                    'observacoes': p.observacoes,
                    'ativo': p.ativo,
                    'ultima_data_analise': p.ultima_data_analise.isoformat() if getattr(p, 'ultima_data_analise', None) else None,
                    'ultima_incerteza': str(p.ultima_incerteza) if getattr(p, 'ultima_incerteza', None) is not None else None,
                    'ultima_tendencia': p.ultima_tendencia or '',
                    'ultima_resultado': p.ultima_resultado or None,
                }
                for p in pontos
            ]
        }
        
        return JsonResponse(data)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao carregar pontos: {str(e)}'
        }, status=400)



@login_required
@require_http_methods(["POST"])
def ponto_calibracao_create(request, instrumento_id):
    """
    API para criar novo ponto de calibração
    RN003: Padrão obrigatório
    RN004: Padrão deve estar ativo
    RN005: Padrão com calibração válida
    RN006: Sequência única por instrumento
    """
    try:
        instrumento = get_object_or_404(Instrumento, pk=instrumento_id)
        data = json.loads(request.body)
                
        ponto = PontoCalibracao(
            instrumento=instrumento,
            sequencia=data['sequencia'],
            descricao=data['descricao'],
            valor_nominal=data.get('valor_nominal') or None,
            valor_minimo=data.get('valor_minimo') or None,
            valor_maximo=data.get('valor_maximo') or None,
            unidade=data['unidade'],
            tolerancia_mais=data.get('tolerancia_mais') or None,
            tolerancia_menos=data.get('tolerancia_menos') or None,
            observacoes=data.get('observacoes', ''),
            ativo=data.get('ativo', True),
        )
        
        # Validação customizada (RN004 e RN005)
        try:
            ponto.clean()
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'message': str(e.message_dict if hasattr(e, 'message_dict') else e)
            }, status=400)
        
        ponto.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Ponto de calibração cadastrado com sucesso!',
            'ponto': {
                'id': ponto.id,
                'sequencia': ponto.sequencia,
            }
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao cadastrar ponto: {str(e)}'
        }, status=400)


@login_required
@require_http_methods(["PUT"])
def ponto_calibracao_update(request, pk):
    """API para atualizar ponto de calibração"""
    try:
        ponto = get_object_or_404(PontoCalibracao, pk=pk)
        data = json.loads(request.body)
        
        ponto.sequencia = data.get('sequencia', ponto.sequencia)
        ponto.descricao = data.get('descricao', ponto.descricao)
        ponto.valor_nominal = data.get('valor_nominal', ponto.valor_nominal)
        ponto.valor_minimo = data.get('valor_minimo', ponto.valor_minimo)
        ponto.valor_maximo = data.get('valor_maximo', ponto.valor_maximo)
        ponto.unidade = data.get('unidade', ponto.unidade)
        ponto.tolerancia_mais = data.get('tolerancia_mais') or None
        ponto.tolerancia_menos = data.get('tolerancia_menos') or None
        ponto.observacoes = data.get('observacoes', ponto.observacoes)
        ponto.ativo = data.get('ativo', ponto.ativo)
                
        # Validação customizada
        try:
            ponto.clean()
        except ValidationError as e:
            return JsonResponse({
                'success': False,
                'message': str(e.message_dict if hasattr(e, 'message_dict') else e)
            }, status=400)
        
        ponto.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Ponto de calibração atualizado com sucesso!'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao atualizar ponto: {str(e)}'
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def ponto_calibracao_delete(request, pk):
    """
    API para deletar ponto de calibração
    RN001: Instrumento deve ter pelo menos 1 ponto
    """
    try:
        ponto = get_object_or_404(PontoCalibracao, pk=pk)
        instrumento = ponto.instrumento
        
        # Validar se é o último ponto (RN001)
        total_pontos = instrumento.pontos_calibracao.count()
        if total_pontos <= 1:
            return JsonResponse({
                'success': False,
                'message': 'Não é possível excluir o último ponto de calibração. O instrumento deve ter pelo menos 1 ponto.'
            }, status=400)
        
        sequencia = ponto.sequencia
        ponto.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Ponto {sequencia} deletado com sucesso!'
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': f'Erro ao deletar ponto: {str(e)}'
        }, status=400)
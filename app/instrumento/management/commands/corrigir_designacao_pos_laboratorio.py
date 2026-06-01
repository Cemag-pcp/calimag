"""
Corrige instrumentos em dois cenários:

Caso A: StatusInstrumento mais recente é "Entregue ao funcionário X"
        mas o FK funcionario está nulo. Ocorre quando o status foi
        criado sem o FK (scripts de importação antigos).
        → Preenche o FK buscando Funcionario pelo nome do tipo_status.

Caso B: StatusInstrumento mais recente é "Recebido do laboratório X"
        (instrumento voltou do lab mas nunca foi re-designado).
        Ativado apenas com a flag --restaurar-pos-laboratorio.
        → Busca a posse anterior ao envio e re-designa automaticamente.

Uso:
  python manage.py corrigir_designacao_pos_laboratorio --dry-run
  python manage.py corrigir_designacao_pos_laboratorio
  python manage.py corrigir_designacao_pos_laboratorio --restaurar-pos-laboratorio --dry-run
  python manage.py corrigir_designacao_pos_laboratorio --restaurar-pos-laboratorio
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from app.cadastro.models import Funcionario, Instrumento
from app.instrumento.models import FuncionarioInstrumento, StatusInstrumento

PREFIX_ENTREGUE = 'Entregue ao funcionário '
PREFIX_RECEBIDO = 'Recebido do laborat'
PREFIX_ENVIADO = 'Enviado ao laborat'


def _posse_anterior_ao_envio(instrumento):
    """Retorna o FuncionarioInstrumento fechado antes do último envio ao lab."""
    ultimo_envio = (
        StatusInstrumento.objects
        .filter(instrumento=instrumento, tipo_status__istartswith=PREFIX_ENVIADO)
        .order_by('-data_entrega')
        .first()
    )
    if not ultimo_envio:
        return None
    posse = (
        FuncionarioInstrumento.objects
        .filter(instrumento=instrumento, funcionario__isnull=False, data_fim__isnull=False,
                data_fim=ultimo_envio.data_entrega)
        .order_by('-data_inicio')
        .first()
    )
    if not posse:
        posse = (
            FuncionarioInstrumento.objects
            .filter(instrumento=instrumento, funcionario__isnull=False, data_fim__isnull=False,
                    data_fim__lte=ultimo_envio.data_entrega)
            .order_by('-data_fim')
            .first()
        )
    return posse


def _criar_posse_e_status(instrumento, funcionario, dry_run, stdout):
    """Cria FuncionarioInstrumento ativo e StatusInstrumento 'Entregue ao funcionário X'."""
    has_active = FuncionarioInstrumento.objects.filter(
        instrumento=instrumento,
        funcionario=funcionario,
        data_fim__isnull=True,
        ativo=True,
    ).exists()
    if has_active:
        stdout.write(f'    -> já tem posse ativa para {funcionario.nome}, apenas FK atualizado')
        return
    now = timezone.now()
    if not dry_run:
        FuncionarioInstrumento.objects.filter(
            instrumento=instrumento, data_fim__isnull=True,
        ).update(data_fim=now, ativo=False)
        FuncionarioInstrumento.objects.create(
            funcionario=funcionario,
            instrumento=instrumento,
            data_inicio=now,
            data_fim=None,
            observacoes='Restaurado pelo comando corrigir_designacao_pos_laboratorio',
            ativo=True,
        )
        StatusInstrumento.objects.create(
            instrumento=instrumento,
            funcionario=funcionario,
            laboratorio=None,
            data_entrega=now,
            data_devolucao=None,
            data_recebimento=None,
            observacoes='Restaurado pelo comando corrigir_designacao_pos_laboratorio',
            tipo_status=f'Entregue ao funcionário {funcionario.nome}',
        )


class Command(BaseCommand):
    help = 'Corrige designação de funcionários após retorno do laboratório'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Mostra o que seria corrigido sem salvar')
        parser.add_argument('--restaurar-pos-laboratorio', action='store_true',
                            help='Também re-designa instrumentos com último status "Recebido do laboratório"')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        restaurar = options['restaurar_pos_laboratorio']
        fixed_a = fixed_b = skipped = 0

        # ── Caso A: "Entregue ao funcionário X" com FK nulo ──────────────────
        self.stdout.write(self.style.HTTP_INFO('=== Caso A: FK funcionario nulo ==='))
        for instrumento in Instrumento.objects.all():
            latest = (
                StatusInstrumento.objects
                .filter(instrumento=instrumento)
                .order_by('-data_entrega', '-id')
                .first()
            )
            if not latest:
                continue
            tipo = latest.tipo_status or ''
            if not tipo.startswith(PREFIX_ENTREGUE):
                continue
            if latest.funcionario_id is not None:
                continue

            nome = tipo[len(PREFIX_ENTREGUE):].strip()
            if not nome:
                skipped += 1
                continue

            funcionario = Funcionario.objects.filter(nome__iexact=nome).first()
            if not funcionario:
                self.stdout.write(
                    self.style.WARNING(f'[SKIP] {instrumento.codigo}: "{nome}" nao encontrado')
                )
                skipped += 1
                continue

            self.stdout.write(
                f'[{"DRY" if dry_run else "FIX"}] {instrumento.codigo}: FK -> {funcionario.nome}'
            )
            if not dry_run:
                with transaction.atomic():
                    latest.funcionario = funcionario
                    latest.save(update_fields=['funcionario'])
                    _criar_posse_e_status(instrumento, funcionario, dry_run, self.stdout)
            fixed_a += 1

        # ── Caso B: último status "Recebido do laboratório X" ────────────────
        if restaurar:
            self.stdout.write(self.style.HTTP_INFO('=== Caso B: Recebido do lab sem re-designacao ==='))
            from django.db.models import OuterRef, Subquery
            latest_qs = StatusInstrumento.objects.filter(
                instrumento=OuterRef('pk')
            ).order_by('-data_entrega', '-id')
            candidatos = Instrumento.objects.annotate(
                ultimo_tipo=Subquery(latest_qs.values('tipo_status')[:1])
            ).filter(ultimo_tipo__istartswith=PREFIX_RECEBIDO)

            for instrumento in candidatos:
                posse = _posse_anterior_ao_envio(instrumento)
                if not posse:
                    self.stdout.write(
                        self.style.WARNING(
                            f'[SKIP] {instrumento.codigo}: sem posse anterior identificavel'
                        )
                    )
                    skipped += 1
                    continue

                self.stdout.write(
                    f'[{"DRY" if dry_run else "FIX"}] {instrumento.codigo}: '
                    f're-designar para {posse.funcionario.nome}'
                )
                if not dry_run:
                    with transaction.atomic():
                        _criar_posse_e_status(instrumento, posse.funcionario, dry_run, self.stdout)
                fixed_b += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nConcluido: caso A={fixed_a}, caso B={fixed_b} corrigidos | {skipped} ignorados'
        ))

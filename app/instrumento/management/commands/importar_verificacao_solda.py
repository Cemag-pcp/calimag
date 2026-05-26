import csv
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from app.cadastro.models import Instrumento, PontoCalibracao
from app.instrumento.models import (
    CertificadoCalibracao,
    FuncionarioInstrumento,
    StatusInstrumento,
    StatusPontoCalibracao,
)


CSV_HEADERS = [
    "codigo",
    "tensao_nominal",
    "tensao_1",
    "tensao_2",
    "tensao_3",
    "incerteza_tensao",
    "corrente_nominal",
    "corrente_1",
    "corrente_2",
    "corrente_3",
    "incerteza_corrente",
    "observacoes",
]


@dataclass
class CsvRow:
    codigo: str
    tensao_nominal: Decimal | None
    tensao_medicoes: list[Decimal]
    incerteza_tensao: Decimal | None
    corrente_nominal: Decimal | None
    corrente_medicoes: list[Decimal]
    incerteza_corrente: Decimal | None
    observacoes: str


class Command(BaseCommand):
    help = (
        "Importa medições de verificação de máquinas de solda a partir de CSV. "
        "Sem --apply, roda em dry-run e só mostra o que seria feito."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Caminho do arquivo CSV.")
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Grava no banco. Sem esta flag, executa apenas dry-run.",
        )
        parser.add_argument(
            "--recebimento-data",
            type=str,
            default=None,
            help="Data/hora ISO para usar no recebimento e na análise. Ex: 2026-05-22T10:00:00-03:00",
        )
        parser.add_argument(
            "--certificado-link",
            type=str,
            default="-",
            help="Link do certificado a usar ao receber itens ainda enviados. Padrão: '-'.",
        )
        parser.add_argument(
            "--laboratorio-nome",
            type=str,
            default="CEMAG",
            help="Laboratório padrão para envios/recebimentos automáticos.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"]).expanduser()
        if not csv_path.exists():
            raise CommandError(f"Arquivo não encontrado: {csv_path}")

        apply_changes = bool(options["apply"])
        operation_dt = self._parse_operation_dt(options.get("recebimento_data"))
        rows = self._load_csv_rows(csv_path)
        instrument_map = self._load_instrument_data([row.codigo for row in rows])

        summary = Counter()
        action_lines: list[str] = []

        db_block = transaction.atomic if apply_changes else transaction.atomic
        with db_block():
            for row in rows:
                outcome = self._process_row(
                    row=row,
                    instrument_map=instrument_map,
                    apply_changes=apply_changes,
                    operation_dt=operation_dt,
                    certificado_link=options["certificado_link"],
                    laboratorio_nome=options["laboratorio_nome"],
                )
                summary[outcome["status"]] += 1
                action_lines.extend(outcome["lines"])

            if not apply_changes:
                transaction.set_rollback(True)

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Resumo"))
        self.stdout.write(f"Modo: {'APPLY' if apply_changes else 'DRY-RUN'}")
        self.stdout.write(f"Arquivo: {csv_path}")
        self.stdout.write(f"Linhas processadas: {len(rows)}")
        for key in sorted(summary):
            self.stdout.write(f"{key}: {summary[key]}")

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Detalhes"))
        for line in action_lines:
            self.stdout.write(line)

    def _parse_operation_dt(self, raw_value):
        if not raw_value:
            return timezone.now()
        parsed = None
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            parsed = None
        if parsed is None:
            for fmt in ("%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
                try:
                    parsed = datetime.strptime(raw_value, fmt)
                    break
                except ValueError:
                    continue
        if parsed is None:
            raise CommandError(f"--recebimento-data inválida: {raw_value}")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def _read_csv_text(self, csv_path: Path) -> str:
        raw = csv_path.read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise CommandError("Não foi possível decodificar o CSV.")

    def _load_csv_rows(self, csv_path: Path) -> list[CsvRow]:
        text = self._read_csv_text(csv_path)
        reader = csv.reader(text.splitlines())
        all_rows = [row for row in reader if any((cell or "").strip() for cell in row)]
        if len(all_rows) < 2:
            raise CommandError("CSV vazio ou sem linhas de dados.")

        data_rows = all_rows[1:]
        parsed_rows: list[CsvRow] = []
        for index, row in enumerate(data_rows, start=2):
            padded = row + [""] * (len(CSV_HEADERS) - len(row))
            padded = padded[: len(CSV_HEADERS)]
            codigo = padded[0].strip()
            if not codigo:
                raise CommandError(f"Linha {index}: código da máquina vazio.")
            parsed_rows.append(
                CsvRow(
                    codigo=codigo,
                    tensao_nominal=self._to_decimal(padded[1]),
                    tensao_medicoes=[
                        value
                        for value in (
                            self._to_decimal(padded[2]),
                            self._to_decimal(padded[3]),
                            self._to_decimal(padded[4]),
                        )
                        if value is not None
                    ],
                    incerteza_tensao=self._to_decimal(padded[5]),
                    corrente_nominal=self._to_decimal(padded[6]),
                    corrente_medicoes=[
                        value
                        for value in (
                            self._to_decimal(padded[7]),
                            self._to_decimal(padded[8]),
                            self._to_decimal(padded[9]),
                        )
                        if value is not None
                    ],
                    incerteza_corrente=self._to_decimal(padded[10]),
                    observacoes=padded[11].strip(),
                )
            )
        return parsed_rows

    def _to_decimal(self, raw_value):
        if raw_value is None:
            return None
        text = str(raw_value).strip()
        if not text:
            return None
        normalized = text.replace(",", ".")
        try:
            return Decimal(normalized)
        except InvalidOperation:
            return None

    def _load_instrument_data(self, codes: list[str]):
        latest_status = StatusInstrumento.objects.filter(
            instrumento=OuterRef("pk")
        ).order_by("-data_entrega", "-id")
        last_envio = StatusInstrumento.objects.filter(
            instrumento=OuterRef("pk"),
            tipo_status__istartswith="Enviado ao laborat",
        ).order_by("-data_entrega", "-id")
        last_receb = StatusInstrumento.objects.filter(
            instrumento=OuterRef("pk"),
            tipo_status__istartswith="Recebido do laborat",
            data_recebimento__isnull=False,
        ).order_by("-data_recebimento", "-id")
        latest_cert = CertificadoCalibracao.objects.filter(
            status__instrumento=OuterRef("pk")
        ).order_by("-data_criacao")
        fallback = timezone.make_aware(datetime(1900, 1, 1))

        qs = (
            Instrumento.objects.filter(codigo__in=codes)
            .annotate(
                status_tipo=Subquery(latest_status.values("tipo_status")[:1]),
                last_status_id=Subquery(latest_status.values("id")[:1]),
                last_envio_data=Subquery(last_envio.values("data_entrega")[:1]),
                last_recebimento_data=Subquery(last_receb.values("data_recebimento")[:1]),
                ultimo_certificado=Subquery(latest_cert.values("link")[:1]),
                total_pontos=Count(
                    "pontos_calibracao",
                    filter=Q(pontos_calibracao__ativo=True),
                    distinct=True,
                ),
            )
            .annotate(
                pontos_analisados_count=Count(
                    "pontos_calibracao__status_pontos",
                    filter=Q(
                        pontos_calibracao__status_pontos__data_criacao__gte=Coalesce(
                            F("last_envio_data"),
                            Value(fallback),
                        )
                    ),
                    distinct=True,
                )
            )
            .prefetch_related("pontos_calibracao")
        )
        return {instrumento.codigo: instrumento for instrumento in qs}

    def _process_row(
        self,
        row,
        instrument_map,
        apply_changes,
        operation_dt,
        certificado_link,
        laboratorio_nome,
    ):
        instrumento = instrument_map.get(row.codigo)
        if not instrumento:
            return {
                "status": "not_found",
                "lines": [f"[NOT_FOUND] {row.codigo}: instrumento não cadastrado."],
            }

        status_tipo = instrumento.status_tipo or ""
        responsavel_original = self._get_current_responsavel(instrumento)
        returned = bool(
            instrumento.last_recebimento_data
            and instrumento.last_envio_data
            and instrumento.last_recebimento_data >= instrumento.last_envio_data
            and status_tipo.startswith("Recebido do laborat")
        )
        sent_open = status_tipo.startswith("Enviado ao laborat")
        send_dt, receive_dt, analysis_dt, restore_dt = self._build_timeline(
            instrumento=instrumento,
            sent_open=sent_open,
            operation_dt=operation_dt,
        )

        if sent_open:
            if apply_changes:
                instrumento = self._receive_instrument(
                    instrumento=instrumento,
                    operation_dt=receive_dt,
                    certificado_link=certificado_link,
                    laboratorio_nome=laboratorio_nome,
                )
            receive_line = (
                f"[RECEIVE{'D' if apply_changes else ''}] {row.codigo}: "
                f"status atual '{status_tipo}' -> receber com certificado '{certificado_link}'."
            )
            returned = True
        elif not returned:
            if apply_changes:
                instrumento = self._send_instrument(
                    instrumento=instrumento,
                    operation_dt=send_dt,
                    laboratorio_nome=laboratorio_nome,
                )
                instrumento = self._receive_instrument(
                    instrumento=instrumento,
                    operation_dt=receive_dt,
                    certificado_link=certificado_link,
                    laboratorio_nome=laboratorio_nome,
                )
            receive_line = (
                f"[SEND_RECEIVE{'D' if apply_changes else ''}] {row.codigo}: "
                f"status atual '{status_tipo or '-'}' -> enviar para {laboratorio_nome}, "
                f"receber com certificado '{certificado_link}'."
            )
            returned = True
        else:
            receive_line = (
                f"[SKIP_RECEIVE] {row.codigo}: status atual '{status_tipo or '-'}'."
            )

        if not returned:
            return {
                "status": "skipped_state",
                "lines": [
                    receive_line,
                    f"[SKIP_ANALYSIS] {row.codigo}: não está em estado elegível para análise.",
                ],
            }

        pontos_ativos = list(
            PontoCalibracao.objects.filter(instrumento=instrumento, ativo=True).order_by("sequencia")
        )
        mapped_points = self._map_points(row, pontos_ativos)
        if mapped_points["errors"]:
            lines = [receive_line]
            lines.extend(f"[MAP_ERROR] {row.codigo}: {error}" for error in mapped_points["errors"])
            return {"status": "mapping_error", "lines": lines}

        analysis_lines = [receive_line]
        for plan in mapped_points["plans"]:
            analysis_lines.append(
                self._describe_plan(
                    code=row.codigo,
                    plan=plan,
                    apply_changes=apply_changes,
                )
            )
            if apply_changes:
                self._upsert_point_nominal_and_status(
                    point=plan["point"],
                    nominal=plan["nominal"],
                    incerteza=plan["incerteza"],
                    media=plan["media"],
                    tendencia=plan["tendencia"],
                    resultado=plan["resultado"],
                    observacoes=plan["observacoes"],
                    operation_dt=analysis_dt,
                )

        if responsavel_original:
            restore_line = (
                f"[{'RESTORE_OWNER' if not apply_changes else 'RESTORED_OWNER'}] "
                f"{row.codigo}: reatribuir para {responsavel_original.nome} ({responsavel_original.matricula})."
            )
            analysis_lines.append(restore_line)
            if apply_changes:
                self._restore_responsavel(
                    instrumento=instrumento,
                    funcionario=responsavel_original,
                    operation_dt=restore_dt,
                )

        status = "ready_apply" if not apply_changes else "applied"
        return {"status": status, "lines": analysis_lines}

    def _build_timeline(self, instrumento, sent_open, operation_dt):
        send_dt = instrumento.last_envio_data or operation_dt
        if instrumento.last_envio_data:
            base_dt = max(operation_dt, instrumento.last_envio_data + timedelta(seconds=1))
        else:
            base_dt = operation_dt
        receive_dt = base_dt
        analysis_dt = receive_dt + timedelta(seconds=1)
        restore_dt = analysis_dt + timedelta(seconds=1)
        return send_dt, receive_dt, analysis_dt, restore_dt

    def _get_current_responsavel(self, instrumento):
        open_posse = (
            FuncionarioInstrumento.objects.filter(
                instrumento=instrumento,
                ativo=True,
                data_fim__isnull=True,
                funcionario__isnull=False,
            )
            .select_related("funcionario")
            .order_by("-data_inicio", "-id")
            .first()
        )
        if open_posse:
            return open_posse.funcionario

        open_status = (
            StatusInstrumento.objects.filter(
                instrumento=instrumento,
                tipo_status__istartswith="Entregue ao funcion",
                data_devolucao__isnull=True,
                funcionario__isnull=False,
            )
            .select_related("funcionario")
            .order_by("-data_entrega", "-id")
            .first()
        )
        if open_status:
            return open_status.funcionario

        last_envio = (
            StatusInstrumento.objects.filter(
                instrumento=instrumento,
                tipo_status__istartswith="Enviado ao laborat",
            )
            .order_by("-data_entrega", "-id")
            .first()
        )
        if last_envio:
            posse_qs = (
                FuncionarioInstrumento.objects.filter(
                    instrumento=instrumento,
                    funcionario__isnull=False,
                    data_fim__isnull=False,
                )
                .select_related("funcionario")
            )
            posse = posse_qs.filter(data_fim=last_envio.data_entrega).order_by("-data_inicio", "-id").first()
            if not posse:
                posse = posse_qs.filter(data_fim__lte=last_envio.data_entrega).order_by("-data_fim", "-id").first()
            if posse:
                return posse.funcionario
        return None

    def _send_instrument(self, instrumento, operation_dt, laboratorio_nome):
        StatusInstrumento.objects.filter(
            instrumento=instrumento,
            data_devolucao__isnull=True,
        ).update(data_devolucao=operation_dt)

        FuncionarioInstrumento.objects.filter(
            instrumento=instrumento,
            data_fim__isnull=True,
        ).update(data_fim=operation_dt, ativo=False)

        StatusInstrumento.objects.create(
            instrumento=instrumento,
            funcionario=None,
            laboratorio=None,
            data_entrega=operation_dt,
            data_devolucao=None,
            data_recebimento=None,
            observacoes="Envio automático via importação de verificação de solda.",
            tipo_status=f"Enviado ao laboratório {laboratorio_nome}",
        )
        instrumento.refresh_from_db()
        instrumento.status_tipo = f"Enviado ao laboratório {laboratorio_nome}"
        instrumento.last_envio_data = operation_dt
        return instrumento

    def _receive_instrument(self, instrumento, operation_dt, certificado_link, laboratorio_nome):
        last_sent = (
            StatusInstrumento.objects.filter(
                instrumento=instrumento,
                tipo_status__istartswith="Enviado ao laborat",
                data_recebimento__isnull=True,
            )
            .order_by("-data_entrega")
            .first()
        )
        lab_name = laboratorio_nome or "externo"
        if last_sent and last_sent.tipo_status:
            marker = "Enviado ao laboratório"
            status_text = last_sent.tipo_status.strip()
            if status_text.lower().startswith(marker.lower()):
                extracted = status_text[len(marker) :].strip()
                if extracted:
                    lab_name = extracted

        if last_sent:
            last_sent.data_recebimento = operation_dt
            last_sent.data_devolucao = operation_dt
            last_sent.save(update_fields=["data_recebimento", "data_devolucao"])

        recv_status = StatusInstrumento.objects.create(
            instrumento=instrumento,
            funcionario=None,
            laboratorio=None,
            data_entrega=operation_dt,
            data_devolucao=None,
            data_recebimento=operation_dt,
            observacoes="Recebimento automático via importação de verificação de solda.",
            tipo_status=f"Recebido do laboratório {lab_name}",
        )
        CertificadoCalibracao.objects.create(status=recv_status, link=certificado_link)

        instrumento.refresh_from_db()
        instrumento.status_tipo = recv_status.tipo_status
        instrumento.last_envio_data = last_sent.data_entrega if last_sent else instrumento.last_envio_data
        instrumento.last_recebimento_data = operation_dt
        return instrumento

    def _restore_responsavel(self, instrumento, funcionario, operation_dt):
        FuncionarioInstrumento.objects.filter(
            instrumento=instrumento,
            ativo=True,
        ).update(ativo=False, data_fim=operation_dt)

        StatusInstrumento.objects.filter(
            instrumento=instrumento,
            data_devolucao__isnull=True,
        ).update(data_devolucao=operation_dt)

        FuncionarioInstrumento.objects.create(
            funcionario=funcionario,
            instrumento=instrumento,
            data_inicio=operation_dt,
            data_fim=None,
            observacoes="Reatribuição automática após importação de verificação de solda.",
            ativo=True,
        )
        StatusInstrumento.objects.create(
            instrumento=instrumento,
            funcionario=funcionario,
            laboratorio=None,
            data_entrega=operation_dt,
            data_devolucao=None,
            data_recebimento=None,
            observacoes="Reatribuição automática após importação de verificação de solda.",
            tipo_status=f"Entregue ao funcionário {funcionario.nome}",
        )

    def _map_points(self, row, pontos_ativos):
        errors = []
        plans = []
        unit_map = {}
        for point in pontos_ativos:
            unit_key = (point.unidade or "").upper()
            unit_map.setdefault(unit_key, []).append(point)

        for point_type, nominal, medicoes, incerteza, unit in (
            ("Tensão", row.tensao_nominal, row.tensao_medicoes, row.incerteza_tensao, "V"),
            ("Corrente", row.corrente_nominal, row.corrente_medicoes, row.incerteza_corrente, "A"),
        ):
            point = self._pick_point(unit_map.get(unit, []), point_type)
            if point is None:
                errors.append(f"ponto de {point_type.lower()} com unidade {unit} não encontrado.")
                continue
            if len(medicoes) != 3:
                errors.append(f"{point_type}: esperado 3 medições, encontrado {len(medicoes)}.")
                continue
            if nominal is None:
                errors.append(f"{point_type}: valor nominal ausente no CSV.")
                continue
            if incerteza is None:
                errors.append(f"{point_type}: incerteza ausente no CSV.")
                continue

            media = (sum(medicoes) / Decimal("3")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            tendencia = (media + incerteza - nominal).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            resultado = ""
            if point.tolerancia_mais is not None:
                resultado = "aprovado" if abs(tendencia) <= point.tolerancia_mais else "reprovado"

            plans.append(
                {
                    "point": point,
                    "tipo": point_type,
                    "nominal": nominal,
                    "medicoes": medicoes,
                    "media": media,
                    "incerteza": incerteza,
                    "tendencia": tendencia,
                    "resultado": resultado,
                    "observacoes": row.observacoes,
                }
            )

        return {"errors": errors, "plans": plans}

    def _pick_point(self, points, expected_label):
        if not points:
            return None
        for point in points:
            if expected_label.lower() in (point.descricao or "").lower():
                return point
        return points[0]

    def _describe_plan(self, code, plan, apply_changes):
        point = plan["point"]
        action = "APPLY_POINT" if apply_changes else "PLAN_POINT"
        resultado = plan["resultado"] or "sem_resultado_auto"
        return (
            f"[{action}] {code} -> ponto {point.sequencia} ({point.descricao}/{point.unidade}) "
            f"nominal={plan['nominal']} media={plan['media']} incerteza={plan['incerteza']} "
            f"tendencia={plan['tendencia']} resultado={resultado}"
        )

    def _upsert_point_nominal_and_status(
        self,
        point,
        nominal,
        incerteza,
        media,
        tendencia,
        resultado,
        observacoes,
        operation_dt,
    ):
        point.valor_nominal = nominal
        point.save(update_fields=["valor_nominal", "data_atualizacao"])

        latest_cert = (
            CertificadoCalibracao.objects.filter(status__instrumento=point.instrumento)
            .order_by("-data_criacao")
            .first()
        )

        status = StatusPontoCalibracao.objects.create(
            ponto_calibracao=point,
            incerteza=incerteza,
            media_medicoes=media,
            tendencia=str(tendencia),
            resultado=resultado or None,
            observacoes=observacoes or "",
            certificado=latest_cert,
        )
        if operation_dt:
            StatusPontoCalibracao.objects.filter(pk=status.pk).update(data_criacao=operation_dt)

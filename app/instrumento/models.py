from django.db import models
from django.utils import timezone

from app.cadastro.models import Funcionario, Instrumento, PontoCalibracao


class FuncionarioInstrumento(models.Model):
    """Relaciona qual funcionário está com qual instrumento."""
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name='instrumentos_em_posse'
    )
    instrumento = models.ForeignKey(
        Instrumento,
        on_delete=models.CASCADE,
        related_name='posses'
    )
    data_inicio = models.DateTimeField('Data Início', default=timezone.now)
    data_fim = models.DateTimeField('Data Fim', null=True, blank=True)
    observacoes = models.TextField('Observações', blank=True)
    ativo = models.BooleanField('Ativo', default=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    data_atualizacao = models.DateTimeField('Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Posse de Instrumento'
        verbose_name_plural = 'Posses de Instrumentos'
        ordering = ['-data_inicio']
        indexes = [
            models.Index(fields=['funcionario', 'instrumento']),
        ]

    def __str__(self):
        return f"{self.funcionario} → {self.instrumento} ({self.data_inicio.strftime('%Y-%m-%d %H:%M')})"


class AssinaturaFuncionarioInstrumento(models.Model):
    """Guarda a assinatura (imagem) do funcionário ao receber/devolver um instrumento."""
    posse = models.ForeignKey(
        FuncionarioInstrumento,
        on_delete=models.CASCADE,
        related_name='assinaturas'
    )
    imagem = models.ImageField('Imagem da Assinatura', upload_to='assinaturas/', blank=False)
    data_assinatura = models.DateTimeField('Data da Assinatura', default=timezone.now)
    observacoes = models.TextField('Observações', blank=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'Assinatura de Posse de Instrumento'
        verbose_name_plural = 'Assinaturas de Posse de Instrumentos'
        ordering = ['-data_assinatura']

    def __str__(self):
        return f"Assinatura {self.posse.funcionario} - {self.data_assinatura.strftime('%Y-%m-%d %H:%M')}"


class StatusInstrumento(models.Model):
    """Estado atual do instrumento: registra entrega e devolução.

    Instrumentos com `data_devolucao` vazia estão atualmente com o funcionário.
    
    Pode ter tipos de status:
        - Enviado ao lab
        - Recebido do lab
        - Entregue ao funcionário x
        - Devolvido pelo funcionário x
    """
    instrumento = models.ForeignKey(
        Instrumento,
        on_delete=models.CASCADE,
        related_name='status_historico'
    )
    funcionario = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name='funcionario_status_instrumentos',
        null=True,
        blank=True
    )
    laboratorio = models.ForeignKey(
        Funcionario,
        on_delete=models.CASCADE,
        related_name='laboratorio_status_instrumentos',
        null=True,
        blank=True
    )   
    tipo_status = models.CharField('Tipo de Status', max_length=100, null=True, blank=True)
    data_entrega = models.DateTimeField('Data Entrega', default=timezone.now)
    data_devolucao = models.DateTimeField('Data Devolução', null=True, blank=True)
    data_recebimento = models.DateTimeField('Data Recebimento', null=True, blank=True)
    observacoes = models.TextField('Observações', blank=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'Status do Instrumento'
        verbose_name_plural = 'Status dos Instrumentos'
        ordering = ['-data_entrega']
        indexes = [
            models.Index(fields=['instrumento', 'funcionario']),
        ]

    def __str__(self):
        status = 'Com' if not self.data_devolucao else 'Devolvido'
        return f"{self.instrumento.codigo} - {status} por {self.funcionario} ({self.data_entrega.strftime('%Y-%m-%d %H:%M')})"


class CertificadoCalibracao(models.Model):
    """Certificado gerado ao receber o instrumento da calibração.

    Vinculado a um `StatusInstrumento` (normalmente o status de recebimento).
    """

    status = models.ForeignKey(
        StatusInstrumento,
        on_delete=models.CASCADE,
        related_name='certificados'
    )
    link = models.URLField('Link do Certificado', max_length=500)
    data_criacao = models.DateTimeField('Data de Criação', auto_now_add=True)

    class Meta:
        verbose_name = 'Certificado de Calibração'
        verbose_name_plural = 'Certificados de Calibração'
        ordering = ['-data_criacao']

    def __str__(self):
        return f"Certificado #{self.id} ({self.data_criacao.strftime('%Y-%m-%d')})"

class StatusPontoCalibracao(models.Model):
    """Registro do resultado/avaliação de um ponto de calibração.

    - vinculado a `PontoCalibracao`
    - pode referenciar um `CertificadoCalibracao` (opcional)
    - responsável é um `Funcionario` (deve ser preenchido pelo código usando o usuário logado)
    - data_criacao é definida automaticamente
    """

    RESULTADO_CHOICES = [
        ('aprovado', 'Aprovado'),
        ('reprovado', 'Reprovado'),
    ]

    ponto_calibracao = models.ForeignKey(
        PontoCalibracao,
        on_delete=models.CASCADE,
        verbose_name='Ponto de Calibração',
        related_name='status_pontos'
    )
    incerteza = models.DecimalField('Incerteza', max_digits=6, decimal_places=4, null=True, blank=True)
    tendencia = models.CharField('Tendência', max_length=100, blank=True)
    resultado = models.CharField('Resultado', max_length=10, choices=RESULTADO_CHOICES, null=True, blank=True)
    observacoes = models.TextField('Observações', blank=True)
    responsavel = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Responsável pela Análise',
        related_name='status_pontos_analise'
    )
    data_criacao = models.DateTimeField('Data de Criação', auto_now_add=True)
    certificado = models.ForeignKey(
        'instrumento.CertificadoCalibracao',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Certificado de Calibração',
        related_name='status_pontos'
    )

    class Meta:
        verbose_name = 'Status do Ponto de Calibração'
        verbose_name_plural = 'Status dos Pontos de Calibração'
        ordering = ['-data_criacao']

    def __str__(self):
        return f"{self.ponto_calibracao} - {self.resultado or 'Sem resultado'}"


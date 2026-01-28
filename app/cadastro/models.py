from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone


class Funcionario(models.Model):
    """Modelo para cadastro de funcionários"""
    
    matricula = models.CharField('Matrícula', max_length=20, unique=True)
    nome = models.CharField('Nome Completo', max_length=200)
    email = models.EmailField('E-mail', blank=True, null=True)
    cargo = models.CharField('Cargo', max_length=100, blank=True)
    setor = models.ForeignKey(
        'Setor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Setor',
        related_name='funcionarios'
    )
    telefone = models.CharField('Telefone', max_length=20, blank=True)
    ativo = models.BooleanField('Ativo', default=True)
    data_admissao = models.DateField('Data de Admissão', null=True, blank=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    data_atualizacao = models.DateTimeField('Data de Atualização', auto_now=True)
    
    class Meta:
        verbose_name = 'Funcionário'
        verbose_name_plural = 'Funcionários'
        ordering = ['nome']
    
    def __str__(self):
        return f"{self.matricula} - {self.nome}"


class TipoInstrumento(models.Model):
    """Tipos de instrumento cadastravel (ex: trena, paquímetro, micrômetro)"""
    descricao = models.CharField('Descrição', max_length=100, unique=True)
    ativo = models.BooleanField('Ativo', default=True)
    documento_qualidade = models.CharField('Documento de Qualidade', max_length=100, blank=True)

    class Meta:
        verbose_name = 'Tipo de Instrumento'
        verbose_name_plural = 'Tipos de Instrumento'
        ordering = ['descricao']

    def __str__(self):
        return self.descricao


class Setor(models.Model):
    """Modelo para definir setores da organização (pode ser referenciado por funcionários e instrumentos)"""
    nome = models.CharField('Nome', max_length=100, unique=True)
    descricao = models.TextField('Descrição', blank=True)
    ativo = models.BooleanField('Ativo', default=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    data_atualizacao = models.DateTimeField('Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Setor'
        verbose_name_plural = 'Setores'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Laboratorio(models.Model):
    """Laboratórios onde as calibrações podem ocorrer"""
    nome = models.CharField('Nome', max_length=150, unique=True)
    ativo = models.BooleanField('Ativo', default=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    data_atualizacao = models.DateTimeField('Data de Atualização', auto_now=True)

    class Meta:
        verbose_name = 'Laboratório'
        verbose_name_plural = 'Laboratórios'
        ordering = ['nome']

    def __str__(self):
        return self.nome


class Instrumento(models.Model):
    """Modelo para cadastro de instrumentos de calibração"""
    
    STATUS_CHOICES = [
        ('ativo', 'Ativo'),
        ('inativo', 'Inativo'),
        ('manutencao', 'Em Manutenção'),
        ('descartado', 'Descartado'),
    ]
    
    codigo = models.CharField('Código', max_length=50, unique=True)
    descricao = models.CharField('Descrição', max_length=200, null=True, blank=True)
    # Tipo antigo removido; agora referencia `TipoInstrumento` cadastrado separadamente
    tipo_instrumento = models.ForeignKey(
        TipoInstrumento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Tipo de Instrumento',
        related_name='instrumentos'
    )
    instrumento_controlado = models.BooleanField('Instrumento Controlado', default=False, help_text='Indica se o instrumento é controlado')
    fabricante = models.CharField('Fabricante', max_length=100, blank=True)
    modelo = models.CharField('Modelo', max_length=100, blank=True)
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES, default='ativo')
    observacoes = models.TextField('Observações', blank=True)
    data_aquisicao = models.DateField('Data de Aquisição', null=True, blank=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    data_atualizacao = models.DateTimeField('Data de Atualização', auto_now=True)
    periodicidade_calibracao = models.PositiveIntegerField(
        'Periodicidade de Calibração (dias)',
        default=365,
        help_text='Intervalo em dias entre calibrações para este ponto'
    )

    class Meta:
        verbose_name = 'Instrumento'
        verbose_name_plural = 'Instrumentos'
        ordering = ['codigo']
    
    def __str__(self):
        return f"{self.codigo} - {self.descricao}"
    
    def clean(self):
        """Valida que o instrumento tem pelo menos um ponto de calibração"""
        super().clean()
        if self.pk:  # Só valida se já existe (update)
            if not self.pontos_calibracao.exists():
                raise ValidationError(
                    'O instrumento deve ter pelo menos um ponto de calibração cadastrado.'
                )
    
    @property
    def total_pontos_calibracao(self):
        """Retorna o total de pontos de calibração do instrumento"""
        return self.pontos_calibracao.count()


class PontoCalibracao(models.Model):
    """Modelo para cadastro de pontos de calibração de cada instrumento"""
    
    UNIDADE_CHOICES = [
        ('mm', 'Milímetros (mm)'),
        ('cm', 'Centímetros (cm)'),
        ('m', 'Metros (m)'),
        ('kg', 'Quilogramas (kg)'),
        ('g', 'Gramas (g)'),
        ('°C', 'Graus Celsius (°C)'),
        ('°F', 'Graus Fahrenheit (°F)'),
        ('Pa', 'Pascal (Pa)'),
        ('bar', 'Bar (bar)'),
        ('psi', 'PSI (psi)'),
        ('V', 'Volts (V)'),
        ('A', 'Ampere (A)'),
        ('Ω', 'Ohm (Ω)'),
        ('Hz', 'Hertz (Hz)'),
        ('rpm', 'RPM (rpm)'),
        ('°', 'Graus (°)'),
        ('Ohms', 'Ohms'),
        ('Kg', 'Quilogramas (Kg)'),
        ('m²/s', 'm²/s'),
        ('HRC', 'Dureza Rockwell C (HRC)'),
        ('L/min', 'Litros por minuto (L/min)'),
        ('Bar', 'Bar (Bar)'),
        ('kgf/cm²', 'Quilograma-força por cm² (kgf/cm²)'),
        ('μm', 'Micrômetro (μm)'),
        ('-', 'Sem unidade (-)'),
        ('V-AC', 'Volts AC (V-AC)'),
        ('UR', 'Umidade Relativa (UR)'),
        ('dB', 'Decibel (dB)'),
        ('outros', 'Outros'),
    ]
    
    instrumento = models.ForeignKey(
        Instrumento,
        on_delete=models.CASCADE,
        verbose_name='Instrumento',
        related_name='pontos_calibracao'
    )
    sequencia = models.PositiveIntegerField(
        'Sequência',
        help_text='Ordem do ponto de calibração'
    )
    descricao = models.CharField('Descrição do Ponto', max_length=200)
    valor_nominal = models.DecimalField(
        'Valor Nominal',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Valor do ponto de calibração (pode ser calculado como média da faixa)'
    )
    valor_minimo = models.DecimalField(
        'Valor Mínimo',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Início da faixa do ponto (ex: 0)'
    )
    valor_maximo = models.DecimalField(
        'Valor Máximo',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text='Fim da faixa do ponto (ex: 600)'
    )
    unidade = models.CharField('Unidade', max_length=20, choices=UNIDADE_CHOICES)
    tolerancia_mais = models.DecimalField(
        'Tolerância (+)',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    tolerancia_menos = models.DecimalField(
        'Tolerância (-)',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    observacoes = models.TextField('Observações', blank=True)
    ativo = models.BooleanField('Ativo', default=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    data_atualizacao = models.DateTimeField('Data de Atualização', auto_now=True)
    
    class Meta:
        verbose_name = 'Ponto de Calibração'
        verbose_name_plural = 'Pontos de Calibração'
        ordering = ['instrumento', 'sequencia']
        unique_together = [['instrumento', 'sequencia']]
    
    def __str__(self):
        if self.valor_minimo is not None and self.valor_maximo is not None:
            return f"{self.instrumento.codigo} - Ponto {self.sequencia}: {self.valor_minimo} a {self.valor_maximo} {self.unidade}"
        return f"{self.instrumento.codigo} - Ponto {self.sequencia}: {self.valor_nominal or '-'} {self.unidade}"
    
class HistoricoCalibracao(models.Model):
    """Modelo para registro de histórico de calibrações realizadas"""
    
    STATUS_CHOICES = [
        ('aprovado', 'Aprovado'),
        ('reprovado', 'Reprovado'),
        ('condicional', 'Condicional'),
    ]
    
    ponto_calibracao = models.ForeignKey(
        PontoCalibracao,
        on_delete=models.CASCADE,
        verbose_name='Ponto de Calibração',
        related_name='historico'
    )
    data_calibracao = models.DateTimeField('Data da Calibração', default=timezone.now)
    valor_medido = models.DecimalField(
        'Valor Medido',
        max_digits=10,
        decimal_places=4
    )
    desvio = models.DecimalField(
        'Desvio',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    incerteza = models.DecimalField(
        'Incerteza',
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    status = models.CharField('Status', max_length=20, choices=STATUS_CHOICES)
    executado_por = models.ForeignKey(
        Funcionario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Executado por',
        related_name='calibracoes_executadas'
    )
    certificado = models.CharField('Número do Certificado', max_length=100, blank=True)
    observacoes = models.TextField('Observações', blank=True)
    data_cadastro = models.DateTimeField('Data de Cadastro', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Histórico de Calibração'
        verbose_name_plural = 'Históricos de Calibração'
        ordering = ['-data_calibracao']
    
    def __str__(self):
        return f"{self.ponto_calibracao} - {self.data_calibracao.strftime('%d/%m/%Y')}"
    
    def save(self, *args, **kwargs):
        """Calcula o desvio automaticamente"""
        if self.valor_medido and self.ponto_calibracao:
            self.desvio = self.valor_medido - self.ponto_calibracao.valor_nominal
        # If nominal not provided but min/max present, set nominal as midpoint for backward compatibility
        if (self.valor_nominal is None or self.valor_nominal == '') and self.valor_minimo is not None and self.valor_maximo is not None:
            try:
                self.valor_nominal = (self.valor_minimo + self.valor_maximo) / 2
            except Exception:
                pass
        super().save(*args, **kwargs)



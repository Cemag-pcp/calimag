from django.contrib import admin
from django.utils.html import format_html
from .models import Funcionario, Instrumento, PontoCalibracao, HistoricoCalibracao, TipoInstrumento, Setor, Laboratorio


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = ('matricula', 'nome', 'cargo', 'setor', 'ativo_badge', 'data_admissao')
    list_filter = ('ativo', 'setor', 'cargo')
    search_fields = ('matricula', 'nome', 'email', 'cargo')
    list_per_page = 50
    date_hierarchy = 'data_cadastro'
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('matricula', 'nome', 'email')
        }),
        ('Informações Profissionais', {
            'fields': ('cargo', 'setor', 'telefone', 'data_admissao')
        }),
        ('Status', {
            'fields': ('ativo',)
        }),
    )
    
    def ativo_badge(self, obj):
        if obj.ativo:
            return format_html('<span style="color: green;">✓ Ativo</span>')
        return format_html('<span style="color: red;">✗ Inativo</span>')
    ativo_badge.short_description = 'Status'


class PontoCalibracaoInline(admin.TabularInline):
    model = PontoCalibracao
    extra = 1
    fields = ('sequencia', 'descricao', 'valor_nominal', 'unidade', 'tolerancia_mais', 'tolerancia_menos', 'ativo')

@admin.register(Instrumento)
class InstrumentoAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'descricao', 'tipo_instrumento', 'total_pontos', 'status_badge')
    list_filter = ('tipo_instrumento', 'status')
    search_fields = ('codigo', 'descricao', 'fabricante', 'modelo', 'numero_serie')
    list_per_page = 50
    date_hierarchy = 'data_cadastro'
    inlines = [PontoCalibracaoInline]
    
    fieldsets = (
        ('Identificação', {
            'fields': ('codigo', 'descricao', 'tipo_instrumento', 'instrumento_controlado')
        }),
        ('Especificações Técnicas', {
            'fields': ('fabricante', 'modelo', 'numero_serie', 'faixa_medicao', 'resolucao')
        }),
        # periodicidade agora é por ponto de calibração
        ('Informações Adicionais', {
            'fields': ('status', 'data_aquisicao', 'observacoes'),
            'classes': ('collapse',)
        }),
    )
    
    def total_pontos(self, obj):
        total = obj.total_pontos_calibracao
        if total == 0:
            return format_html('<span style="color: red;">⚠ 0 pontos</span>')
        return format_html(f'<span style="color: green;">{total} ponto(s)</span>')
    total_pontos.short_description = 'Pontos de Calibração'
    
    def status_badge(self, obj):
        colors = {
            'ativo': 'green',
            'inativo': 'gray',
            'manutencao': 'orange',
            'descartado': 'red'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(f'<span style="color: {color}; font-weight: bold;">{obj.get_status_display()}</span>')
    status_badge.short_description = 'Status'


@admin.register(PontoCalibracao)
class PontoCalibracaoAdmin(admin.ModelAdmin):
    list_display = ('instrumento', 'sequencia', 'descricao', 'valor_nominal', 'unidade', 'ativo_badge')
    list_filter = ('ativo', 'unidade', 'instrumento__tipo_instrumento')
    search_fields = ('instrumento__codigo', 'instrumento__descricao', 'descricao')
    list_per_page = 50
    autocomplete_fields = ['instrumento']
    
    fieldsets = (
        ('Instrumento', {
            'fields': ('instrumento',)
        }),
        ('Informações do Ponto', {
                'fields': ('sequencia', 'descricao', 'valor_nominal', 'unidade')
        }),
        ('Tolerâncias', {
            'fields': ('tolerancia_mais', 'tolerancia_menos')
        }),
        ('Observações', {
            'fields': ('observacoes', 'ativo'),
            'classes': ('collapse',)
        }),
    )
    
    def ativo_badge(self, obj):
        if obj.ativo:
            return format_html('<span style="color: green;">✓</span>')
        return format_html('<span style="color: red;">✗</span>')
    ativo_badge.short_description = 'Ativo'


@admin.register(HistoricoCalibracao)
class HistoricoCalibracaoAdmin(admin.ModelAdmin):
    list_display = ('ponto_calibracao', 'data_calibracao', 'valor_medido', 'desvio', 'status_badge', 'executado_por', 'certificado')
    list_filter = ('status', 'data_calibracao', 'executado_por')
    search_fields = ('ponto_calibracao__instrumento__codigo', 'certificado', 'executado_por__nome')
    list_per_page = 50
    date_hierarchy = 'data_calibracao'
    autocomplete_fields = ['ponto_calibracao', 'executado_por']
    readonly_fields = ('desvio',)
    
    fieldsets = (
        ('Ponto de Calibração', {
            'fields': ('ponto_calibracao',)
        }),
        ('Medições', {
            'fields': ('data_calibracao', 'valor_medido', 'desvio', 'incerteza', 'status')
        }),
        ('Execução', {
            'fields': ('executado_por', 'certificado')
        }),
        ('Observações', {
            'fields': ('observacoes',),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        colors = {
            'aprovado': 'green',
            'reprovado': 'red',
            'condicional': 'orange'
        }
        color = colors.get(obj.status, 'gray')
        return format_html(f'<span style="color: {color}; font-weight: bold;">{obj.get_status_display()}</span>')
    status_badge.short_description = 'Status'


# Customizações do admin site
admin.site.site_header = 'Calimag - Administração'
admin.site.site_title = 'Calimag Admin'
admin.site.index_title = 'Gerenciamento de Calibração'


@admin.register(Setor)
class SetorAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    search_fields = ('nome',)
    list_filter = ('ativo',)
    readonly_fields = ('data_cadastro',)


@admin.register(Laboratorio)
class LaboratorioAdmin(admin.ModelAdmin):
    list_display = ('nome', 'ativo')
    search_fields = ('nome',)
    list_filter = ('ativo',)
    readonly_fields = ('data_cadastro',)

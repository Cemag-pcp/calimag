from django.contrib import admin
from .models import FuncionarioInstrumento, AssinaturaFuncionarioInstrumento, StatusInstrumento


@admin.register(FuncionarioInstrumento)
class FuncionarioInstrumentoAdmin(admin.ModelAdmin):
    list_display = ('funcionario', 'instrumento', 'data_inicio', 'data_fim', 'ativo')
    list_filter = ('ativo', 'data_inicio', 'data_fim')
    search_fields = ('funcionario__nome', 'funcionario__matricula', 'instrumento__codigo', 'instrumento__descricao')


@admin.register(AssinaturaFuncionarioInstrumento)
class AssinaturaFuncionarioInstrumentoAdmin(admin.ModelAdmin):
    list_display = ('posse', 'data_assinatura', 'data_cadastro')
    search_fields = ('posse__funcionario__nome', 'posse__instrumento__codigo')


@admin.register(StatusInstrumento)
class StatusInstrumentoAdmin(admin.ModelAdmin):
    list_display = ('instrumento', 'funcionario', 'data_entrega', 'data_devolucao')
    list_filter = ('data_devolucao',)
    search_fields = ('instrumento__codigo', 'funcionario__nome', 'funcionario__matricula')

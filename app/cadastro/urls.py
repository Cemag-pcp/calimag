from django.urls import path
from . import views

app_name = 'cadastro'

urlpatterns = [
    # Instrumentos
    path('instrumentos/', views.instrumentos_list, name='instrumentos_list'),
    path('api/instrumentos/', views.instrumentos_api, name='instrumentos_api'),
    path('api/instrumentos/create/', views.instrumento_create, name='instrumento_create'),
    path('api/instrumentos/<int:pk>/update/', views.instrumento_update, name='instrumento_update'),
    path('api/instrumentos/<int:pk>/delete/', views.instrumento_delete, name='instrumento_delete'),
    
    # Pontos de Calibração
    path('api/instrumentos/<int:instrumento_id>/pontos/', views.pontos_calibracao_api, name='pontos_calibracao_api'),
    path('api/instrumentos/<int:instrumento_id>/pontos/only-ativo/', views.pontos_calibracao_api_only_ativo, name='pontos_calibracao_api_only_ativo'),
    path('api/instrumentos/<int:instrumento_id>/pontos/create/', views.ponto_calibracao_create, name='ponto_calibracao_create'),
    path('api/pontos/<int:pk>/update/', views.ponto_calibracao_update, name='ponto_calibracao_update'),
    path('api/pontos/<int:pk>/delete/', views.ponto_calibracao_delete, name='ponto_calibracao_delete'),
    
    # Tipos de Instrumento
    path('api/tipos_instrumento/', views.tipos_instrumento_api, name='tipos_instrumento_api'),
    path('tipos-instrumento/', views.tipos_instrumento_list, name='tipos_instrumento_list'),
    path('api/tipos_instrumento/create/', views.tipos_instrumento_create, name='tipos_instrumento_create'),
    path('api/tipos_instrumento/<int:pk>/update/', views.tipos_instrumento_update, name='tipos_instrumento_update'),
    path('api/tipos_instrumento/<int:pk>/delete/', views.tipos_instrumento_delete, name='tipos_instrumento_delete'),
    path('api/setores/', views.setores_api, name='setores_api'),
    path('setores/', views.setores_list, name='setores_list'),
    path('api/setores/create/', views.setores_create, name='setores_create'),
    path('api/setores/<int:pk>/update/', views.setores_update, name='setores_update'),
    path('api/setores/<int:pk>/delete/', views.setores_delete, name='setores_delete'),
    
    # Laboratórios
    path('api/laboratorios/', views.laboratorios_api, name='laboratorios_api'),
    path('laboratorios/', views.laboratorios_list, name='laboratorios_list'),
    path('api/laboratorios/create/', views.laboratorios_create, name='laboratorios_create'),
    path('api/laboratorios/<int:pk>/update/', views.laboratorios_update, name='laboratorios_update'),
    path('api/laboratorios/<int:pk>/delete/', views.laboratorios_delete, name='laboratorios_delete'),
        
    # Funcionários API
    path('api/funcionarios/', views.funcionarios_api, name='funcionarios_api'),
    path('funcionarios/', views.funcionarios_list, name='funcionarios_list'),
    path('api/funcionarios/lista/', views.funcionarios_lista_api, name='funcionarios_lista_api'),
    path('api/funcionarios/import/', views.funcionarios_import, name='funcionarios_import'),
    path('api/funcionarios/create/', views.funcionario_create, name='funcionario_create'),
    path('api/funcionarios/<int:pk>/update/', views.funcionario_update, name='funcionario_update'),
    path('api/funcionarios/<int:pk>/delete/', views.funcionario_delete, name='funcionario_delete'),
]

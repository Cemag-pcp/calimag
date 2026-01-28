from django.urls import path
from . import views

app_name = 'instrumento'

urlpatterns = [
	path('', views.list_instrumentos, name='list'),
	path('<int:pk>/', views.detail_instrumento, name='detail'),
	path('api/designar/', views.designar_instrumento, name='designar'),
	path('api/import-entregas/', views.import_entregas_csv, name='import_entregas_csv'),
	path('api/devolver/', views.devolver_instrumento, name='devolver_instrumento'),
	path('api/entregas/', views.entregas_api, name='entregas_api'),
	path('api/historico/<int:instrumento_id>/', views.historico_instrumento, name='historico_instrumento'),
	path('api/ultimo-responsavel/<int:instrumento_id>/', views.ultimo_responsavel_pre_envio, name='ultimo_responsavel_pre_envio'),
	path('api/enviar/', views.enviar_para_calibracao, name='enviar_para_calibracao'),
	path('api/receber/', views.receber_da_calibracao, name='receber_da_calibracao'),
	path('api/status-ponto/', views.registrar_status_ponto, name='registrar_status_ponto'),
	path('api/status/', views.instrumentos_status_api, name='instrumentos_status_api'),
	path('api/indicadores/', views.indicadores_dashboard, name='indicadores_dashboard'),
	path('api/disponiveis/', views.instrumentos_disponiveis, name='instrumentos_disponiveis'),
]

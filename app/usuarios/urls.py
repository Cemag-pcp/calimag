from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('', views.home, name='home'),
    path('pmc/instrumentos/', views.pmc_instrumentos, name='pmc_instrumentos'),
    path('pmc/maquinas-solda/', views.pmc_maquinas_solda, name='pmc_maquinas_solda'),
    path('pmc/gabaritos/', views.pmc_gabaritos, name='pmc_gabaritos'),
    path('entregas/', views.entregas, name='entregas'),
]

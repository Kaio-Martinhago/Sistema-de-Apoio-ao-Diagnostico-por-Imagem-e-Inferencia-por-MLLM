from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('pacientes/novo/', views.cadastro_paciente, name='cadastro_paciente'),
    path('exames/novo/', views.cadastro_exame, name='cadastro_exame'),
    path('api/buscar-pacientes/', views.buscar_paciente_api, name='buscar_paciente_api'), # A rota invisível
]
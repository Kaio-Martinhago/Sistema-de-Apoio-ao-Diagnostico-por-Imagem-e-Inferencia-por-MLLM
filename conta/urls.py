from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),

    path('pacientes/novo/', views.cadastro_paciente, name='cadastro_paciente'),
    path('exames/novo/', views.cadastro_exame, name='cadastro_exame'),
    path('api/buscar-pacientes/', views.buscar_paciente_api, name='buscar_paciente_api'),
    path('criar-conta/', views.criar_conta_medico, name='criar_conta'),
    path('exame/<int:exame_id>/upload/', views.upload_imagens, name='upload_imagens'),
    path('exame/<int:exame_id>/laudar/', views.laudar_exame, name='laudar_exame'),
    path('exames/<int:exame_id>/detalhes/', views.detalhes_exame, name='detalhes_exame'),
    path('historico/', views.historico_paciente, name='historico_paciente'),
    path('api/check-processamento/', views.check_processamento_api, name='check_processamento_api'),
    path('admin-banco/', views.painel_banco, name='painel_banco'),
    path('admin-banco/drop/', views.dropar_tabelas, name='dropar_tabelas'),
    path('admin-banco/popular/', views.recriar_e_popular, name='recriar_e_popular'),
    path('consultas/', views.consultas_relatorios, name='consultas_relatorios'),
]
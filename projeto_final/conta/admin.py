from django.contrib import admin
from .models import Paciente, Medico, Equipamento, Exame, ImagemMedica, ModeloMllm, Inferencia, Laudo

@admin.register(Paciente)
class PacienteAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'cpf', 'data_nascimento', 'telefone')
    search_fields = ('nome_completo', 'cpf')

@admin.register(Medico)
class MedicoAdmin(admin.ModelAdmin):
    list_display = ('nome_completo', 'crm', 'especialidade', 'email_institucional')
    search_fields = ('nome_completo', 'crm')
    list_filter = ('especialidade', 'uf_crm')

@admin.register(Equipamento)
class EquipamentoAdmin(admin.ModelAdmin):
    list_display = ('nome_equipamento', 'numero_serie', 'status_operacional', 'data_ultima_manutencao')
    list_filter = ('status_operacional',)

@admin.register(ModeloMllm)
class ModeloMllmAdmin(admin.ModelAdmin):
    list_display = ('nome_modelo', 'versao', 'arquitetura')

# Os outros modelos deixamos o registro básico, pois serão geridos mais pelas telas da aplicação do que pelo admin
admin.site.register(Exame)
admin.site.register(ImagemMedica)
admin.site.register(Inferencia)
admin.site.register(Laudo)
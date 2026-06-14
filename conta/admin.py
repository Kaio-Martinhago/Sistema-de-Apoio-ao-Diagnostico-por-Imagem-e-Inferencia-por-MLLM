from django.contrib import admin
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from .models import Paciente, Medico, Equipamento, Exame, ImagemMedica, ModeloMllm, Inferencia, Laudo

class BloqueioExclusaoAdmin(admin.ModelAdmin):
    
    def obter_mensagem_erro(self):
        # Descobre qual tabela o usuário está tentando apagar no momento
        nome_modelo = self.model.__name__
        
        msgs_personalizadas = {
            'Equipamento': "O equipamento não pode ser apagado porque já foi utilizado para registrar exames no sistema.",
            'Paciente': "O paciente não pode ser apagado pois já possui exames em seu histórico médico.",
            'Medico': "O médico não pode ser apagado pois possui exames solicitados ou revisões de laudos assinadas.",
            'ModeloMllm': "O modelo de IA não pode ser apagado pois possui inferências e laudos atrelados a ele.",
            'Exame': "O exame não pode ser apagado porque possui imagens médicas, status ou laudos dependentes.",
            'Inferencia': "A inferência não pode ser apagada pois é a base estrutural de imagens ou laudos já gerados.",
            'Laudo': "O laudo não pode ser apagado pois possui uma auditoria/revisão médica atrelada a ele."
        }
        # Se não achar no dicionário, dá uma resposta genérica
        return msgs_personalizadas.get(nome_modelo, "Este registro está sendo usado por outra tabela e não pode ser excluído (ON DELETE RESTRICT).")

    def message_user(self, request, message, level=messages.INFO, extra_tags='', fail_silently=False):
        if getattr(request, 'bloquear_msg_sucesso', False) and level == messages.SUCCESS:
            return
        super().message_user(request, message, level, extra_tags, fail_silently)

    def delete_view(self, request, object_id, extra_context=None):
        try:
            with transaction.atomic():
                return super().delete_view(request, object_id, extra_context)
        except IntegrityError:
            msg = self.obter_mensagem_erro()
            messages.error(request, f"❌ Ação bloqueada: {msg}")
            return HttpResponseRedirect("../../")

    def delete_queryset(self, request, queryset):
        try:
            with transaction.atomic():
                super().delete_queryset(request, queryset)
        except IntegrityError:
            request.bloquear_msg_sucesso = True 
            
            msg = self.obter_mensagem_erro()
            messages.error(request, f"❌ Ação em lote bloqueada: {msg} Nenhum item foi apagado para garantir a integridade do banco.")



@admin.register(Paciente)
class PacienteAdmin(BloqueioExclusaoAdmin):
    list_display = ('nome_completo', 'cpf', 'data_nascimento', 'telefone')
    search_fields = ('nome_completo', 'cpf')

@admin.register(Medico)
class MedicoAdmin(BloqueioExclusaoAdmin):
    list_display = ('nome_completo', 'crm', 'especialidade', 'email_institucional')
    search_fields = ('nome_completo', 'crm')
    list_filter = ('especialidade', 'uf_crm')

@admin.register(Equipamento)
class EquipamentoAdmin(BloqueioExclusaoAdmin):
    list_display = ('nome_equipamento', 'numero_serie', 'status_operacional', 'data_ultima_manutencao')
    list_filter = ('status_operacional',)

@admin.register(ModeloMllm)
class ModeloMllmAdmin(BloqueioExclusaoAdmin):
    list_display = ('nome_modelo', 'versao', 'arquitetura')

@admin.register(Exame)
class ExameAdmin(BloqueioExclusaoAdmin):
    pass

@admin.register(ImagemMedica)
class ImagemMedicaAdmin(BloqueioExclusaoAdmin):
    pass

@admin.register(Inferencia)
class InferenciaAdmin(BloqueioExclusaoAdmin):
    pass

@admin.register(Laudo)
class LaudoAdmin(BloqueioExclusaoAdmin):
    pass
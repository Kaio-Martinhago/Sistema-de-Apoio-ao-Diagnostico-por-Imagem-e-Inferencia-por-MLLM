# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models

class Equipamento(models.Model):
    id_equipamento = models.AutoField(db_column='ID_Equipamento', primary_key=True)  # Field name made lowercase.
    numero_serie = models.CharField(db_column='Numero_Serie', unique=True, max_length=100)  # Field name made lowercase.
    nome_equipamento = models.CharField(db_column='Nome_Equipamento', max_length=100)  # Field name made lowercase.
    status_operacional = models.CharField(db_column='Status_Operacional', max_length=30)  # Field name made lowercase.
    data_ultima_manutencao = models.DateField(db_column='Data_Ultima_Manutencao', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'equipamento'

    def __str__(self):
        return f"{self.nome_equipamento} (S/N: {self.numero_serie})"


class Exame(models.Model):
    id_exame = models.AutoField(db_column='ID_Exame', primary_key=True)  # Field name made lowercase.
    data_hora_solicitacao = models.DateTimeField(db_column='Data_Hora_Solicitacao')  # Field name made lowercase.
    regiao_corpo = models.CharField(db_column='Regiao_Corpo', max_length=100)  # Field name made lowercase.
    observacoes_clinicas = models.TextField(db_column='Observacoes_Clinicas', blank=True, null=True)  # Field name made lowercase.
    id_equipamento = models.ForeignKey(Equipamento, models.DO_NOTHING, db_column='ID_Equipamento')  # Field name made lowercase.
    id_paciente = models.ForeignKey('Paciente', models.DO_NOTHING, db_column='ID_Paciente')  # Field name made lowercase.
    id_medico = models.ForeignKey('Medico', models.DO_NOTHING, db_column='ID_Medico')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'exame'


class ExameStatus(models.Model):
    id_exame_status = models.AutoField(db_column='ID_Exame_Status', primary_key=True)  # Field name made lowercase.
    id_status = models.ForeignKey('Status', models.DO_NOTHING, db_column='ID_Status')  # Field name made lowercase.
    id_exame = models.ForeignKey(Exame, models.DO_NOTHING, db_column='ID_Exame')  # Field name made lowercase.
    data_modificacao = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'exame_status'


class ImagemMedica(models.Model):
    id_imagem = models.AutoField(db_column='ID_Imagem', primary_key=True)  # Field name made lowercase.
    resolucao_largura = models.IntegerField(db_column='Resolucao_Largura')  # Field name made lowercase.
    data_hora_aquisicao = models.DateTimeField(db_column='Data_Hora_Aquisicao')  # Field name made lowercase.
    formato_arquivo = models.CharField(db_column='Formato_Arquivo', max_length=10)  # Field name made lowercase.
    tamanho_arquivo_mb = models.DecimalField(db_column='Tamanho_Arquivo_MB', max_digits=6, decimal_places=2)  # Field name made lowercase.
    caminho_armazenamento = models.CharField(db_column='Caminho_Armazenamento', max_length=255)  # Field name made lowercase.
    resolucao_altura = models.IntegerField(db_column='Resolucao_Altura')  # Field name made lowercase.
    id_exame = models.ForeignKey(Exame, models.DO_NOTHING, db_column='ID_Exame')  # Field name made lowercase.
    id_inferencia = models.ForeignKey('Inferencia', models.DO_NOTHING, db_column='ID_Inferencia', blank=True, null=True)  # Field name made lowercase.
    class Meta:
        managed = False
        db_table = 'imagem_medica'


class Inferencia(models.Model):
    id_inferencia = models.AutoField(db_column='ID_Inferencia', primary_key=True)  # Field name made lowercase.
    data_hora_inicio = models.DateTimeField(db_column='Data_Hora_Inicio')  # Field name made lowercase.
    tempo_processamento = models.IntegerField(db_column='Tempo_Processamento')  # Field name made lowercase.
    status_resultado = models.CharField(db_column='Status_Resultado', max_length=30)  # Field name made lowercase.
    id_modelo = models.ForeignKey('ModeloMllm', models.DO_NOTHING, db_column='ID_Modelo')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'inferencia'


class Laudo(models.Model):
    id_laudo = models.AutoField(db_column='ID_Laudo', primary_key=True)  # Field name made lowercase.
    conteudo_final = models.TextField(db_column='Conteudo_Final', blank=True, null=True)  # Field name made lowercase.
    data_hora_assinatura = models.DateTimeField(db_column='Data_Hora_Assinatura', blank=True, null=True)  # Field name made lowercase.
    status_aprovacao = models.CharField(db_column='Status_Aprovacao', max_length=30, blank=True, null=True)  # Field name made lowercase.
    data_hora_geracao = models.DateTimeField(db_column='Data_Hora_Geracao')  # Field name made lowercase.
    texto_gerado = models.TextField(db_column='Texto_Gerado')  # Field name made lowercase.
    tokens_consumidos = models.IntegerField(db_column='Tokens_Consumidos')  # Field name made lowercase.
    prompt_utilizado = models.TextField(db_column='Prompt_Utilizado')  # Field name made lowercase.
    id_modelo = models.ForeignKey('ModeloMllm', models.DO_NOTHING, db_column='ID_Modelo')  # Field name made lowercase.
    id_inferencia = models.ForeignKey(Inferencia, models.DO_NOTHING, db_column='ID_Inferencia')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'laudo'


class Medico(models.Model):
    id_medico = models.AutoField(db_column='ID_Medico', primary_key=True)  # Field name made lowercase.
    nome_completo = models.CharField(db_column='Nome_Completo', max_length=150)  # Field name made lowercase.
    crm = models.CharField(db_column='CRM', unique=True, max_length=20)  # Field name made lowercase.
    uf_crm = models.CharField(db_column='UF_CRM', max_length=2)  # Field name made lowercase.
    especialidade = models.CharField(db_column='Especialidade', max_length=100)  # Field name made lowercase.
    email_institucional = models.CharField(db_column='Email_Institucional', max_length=150, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'medico'


class ModeloMllm(models.Model):
    id_modelo = models.AutoField(db_column='ID_Modelo', primary_key=True)  # Field name made lowercase.
    nome_modelo = models.CharField(db_column='Nome_Modelo', max_length=100)  # Field name made lowercase.
    versao = models.CharField(db_column='Versao', max_length=50)  # Field name made lowercase.
    arquitetura = models.CharField(db_column='Arquitetura', max_length=100)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'modelo_mllm'


class Paciente(models.Model):
    id_paciente = models.AutoField(db_column='ID_Paciente', primary_key=True)  # Field name made lowercase.
    nome_completo = models.CharField(db_column='Nome_Completo', max_length=150)  # Field name made lowercase.
    cpf = models.CharField(db_column='CPF', unique=True, max_length=11)  # Field name made lowercase.
    data_nascimento = models.DateField(db_column='Data_Nascimento')  # Field name made lowercase.
    sexo = models.CharField(db_column='Sexo', max_length=15)  # Field name made lowercase.
    telefone = models.CharField(db_column='Telefone', max_length=20, blank=True, null=True)  # Field name made lowercase.
    email = models.CharField(db_column='Email', max_length=150, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'paciente'


class RevisaoLaudo(models.Model):
    id_revisao = models.AutoField(db_column='ID_Revisao', primary_key=True)  # Field name made lowercase.
    data_hora_revisao = models.DateTimeField(db_column='Data_Hora_Revisao')  # Field name made lowercase.
    concordancia = models.CharField(db_column='Concordancia', max_length=20)  # Field name made lowercase.
    observacao_tecnica = models.TextField(db_column='Observacao_Tecnica', blank=True, null=True)  # Field name made lowercase.
    id_medico = models.ForeignKey(Medico, models.DO_NOTHING, db_column='ID_Medico')  # Field name made lowercase.
    id_laudo = models.ForeignKey(Laudo, models.DO_NOTHING, db_column='ID_Laudo')  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'revisao_laudo'


class Status(models.Model):
    id_status = models.AutoField(db_column='ID_Status', primary_key=True)  # Field name made lowercase.
    descricao_status = models.CharField(db_column='Descricao_Status', max_length=50)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'status'
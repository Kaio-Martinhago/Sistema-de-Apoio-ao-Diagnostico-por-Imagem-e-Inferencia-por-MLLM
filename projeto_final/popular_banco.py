import os
import django
import random
from datetime import timedelta

# Configura o script para usar o ambiente do seu projeto Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'projeto_final.settings') # Troque 'meu_projeto' se o nome for diferente
django.setup()

from django.utils import timezone
from faker import Faker
from conta.models import (Paciente, Equipamento, Medico, Status, ModeloMllm, 
                         Exame, ExameStatus, ImagemMedica, Inferencia, Laudo, RevisaoLaudo)

fake = Faker('pt_BR')

def popular_banco(quantidade_exames=20):
    """
    print("Limpando dados antigos (opcional, remova se quiser manter)...")
    RevisaoLaudo.objects.all().delete()
    Laudo.objects.all().delete()
    Inferencia.objects.all().delete()
    ImagemMedica.objects.all().delete()
    ExameStatus.objects.all().delete()
    Exame.objects.all().delete()
    Paciente.objects.all().delete()
    Medico.objects.all().delete()
    Equipamento.objects.all().delete()
    Status.objects.all().delete()
    ModeloMllm.objects.all().delete()"""
    print("Criando Status...")
    status_lista = ['Aguardando Imagem', 'Em Processamento IA', 'Aguardando Laudo', 'Concluído']
    status_objs = [Status.objects.create(descricao_status=s) for s in status_lista]

    print("Criando Modelos MLLM")
    modelos_dados = [
        {"nome": "Mixtral", "versao": "3.6", "arq": "Transformer"},
        {"nome": "Qwen2.5", "versao": "32b", "arq": "transformer"},
        {"nome": "LLaVA-Med", "versao": "1.5", "arq": "Transformer"}
    ]
    modelos_objs = [ModeloMllm.objects.create(
        nome_modelo=m["nome"], versao=m["versao"], arquitetura=m["arq"]
    ) for m in modelos_dados]

    print("Criando Médicos...")
    medicos_dados = [
        {"nome": "Dr. Antonio Carlos Sobieranski", "esp": "Radiologia", "crm": "112233"},
        {"nome": "Dr. Anderson Luiz Fernandes Perez", "esp": "Ortopedia", "crm": "445566"},
        {"nome": "Dra. Laura Mendes", "esp": "Traumatologia", "crm": "778899"}
    ]
    medicos_objs = [Medico.objects.create(
        nome_completo=m["nome"], crm=m["crm"], uf_crm="SC", 
        especialidade=m["esp"], email_institucional=f"dr.{m['nome'].split()[-1].lower()}@hospital.com"
    ) for m in medicos_dados]

    print("Criando Equipamentos...")
    equipamentos_objs = [
        Equipamento.objects.create(numero_serie="RX-9000", nome_equipamento="Raio-X Digital", status_operacional="Ativo", data_ultima_manutencao=fake.date_this_year()),
        Equipamento.objects.create(numero_serie="RX-500", nome_equipamento="Raio-X Digital", status_operacional="Ativo", data_ultima_manutencao=fake.date_this_year())
    ]

    print("Criando Pacientes e Exames...")
    for _ in range(quantidade_exames):
        # 1. Cria Paciente
        paciente = Paciente.objects.create(
            nome_completo=fake.name(),
            cpf=fake.cpf().replace('.', '').replace('-', ''),
            data_nascimento=fake.date_of_birth(minimum_age=5, maximum_age=90),
            sexo=random.choice(['Masculino', 'Feminino', 'Outro']),
            telefone=fake.cellphone_number(),
            email=fake.email()
        )

        # 2. Cria Exame
        data_solicitacao = timezone.now() - timedelta(days=random.randint(1, 30))
        exame = Exame.objects.create(
            data_hora_solicitacao=data_solicitacao,
            regiao_corpo=random.choice(['Punho', 'Fêmur', 'Tórax', 'Pé', 'Bacia']),
            observacoes_clinicas="Paciente relata dor aguda após queda.",
            id_equipamento=random.choice(equipamentos_objs),
            id_paciente=paciente,
            id_medico=random.choice(medicos_objs)
        )

        # 3. Registra Status do Exame
        ExameStatus.objects.create(
            id_status=status_objs[-1], # Marca como concluído
            id_exame=exame,
            data_modificacao=data_solicitacao + timedelta(hours=1)
        )

        # 4. Cria Imagem Médica (Simulando DICOM ou PNG)
        imagem = ImagemMedica.objects.create(
            resolucao_largura=1024,
            resolucao_altura=1024,
            data_hora_aquisicao=data_solicitacao + timedelta(minutes=30),
            formato_arquivo=random.choice(['JPG', 'PNG']),
            tamanho_arquivo_mb=random.uniform(5.0, 50.0),
            caminho_armazenamento=f"/storage/imagens/{exame.id_exame}_img.dcm",
            id_exame=exame
        )

        # 5. Cria Inferencia
        modelo_escolhido = random.choice(modelos_objs)
        inferencia = Inferencia.objects.create(
            data_hora_inicio=imagem.data_hora_aquisicao + timedelta(minutes=5),
            tempo_processamento=random.randint(200, 1500), # em milissegundos
            status_resultado="Sucesso",
            id_imagem=imagem,
            id_modelo=modelo_escolhido
        )

        # 6. Cria Laudo gerado pela IA
        laudo = Laudo.objects.create(
            conteudo_final="Fratura detectada com 95% de confiança na região diáfise.",
            data_hora_assinatura=inferencia.data_hora_inicio + timedelta(hours=2),
            status_aprovacao="Aprovado",
            data_hora_geracao=inferencia.data_hora_inicio + timedelta(seconds=2),
            texto_gerado="Bounding box identificada [x, y, w, h]. Fratura linear detectada.",
            tokens_consumidos=random.randint(150, 500),
            prompt_utilizado="Analise a imagem radiológica e aponte possíveis fraturas.",
            id_modelo=modelo_escolhido,
            id_inferencia=inferencia
        )

        # 7. Cria Revisão do Laudo pelo Médico
        RevisaoLaudo.objects.create(
            data_hora_revisao=laudo.data_hora_assinatura,
            concordancia=random.choice(['Total', 'Parcial', 'Discordante']),
            observacao_tecnica="Concordo com a marcação do modelo anatômico.",
            id_medico=exame.id_medico,
            id_laudo=laudo
        )

    print(f"\nBanco populado com sucesso! {quantidade_exames} fluxos completos de exames foram gerados.")

if __name__ == '__main__':
    popular_banco(1) # Altere este número para gerar mais ou menos registros
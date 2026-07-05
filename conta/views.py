from django.db.models import Count, OuterRef, Subquery
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
import requests
from .forms import PacienteForm, ExameForm, MedicoRegistroForm, MultiplaImagemForm, RevisaoLaudoForm
from django.contrib.auth.models import User
from .models import Paciente, Medico, Equipamento, Exame, ModeloMllm, Status, ExameStatus, ImagemMedica, Inferencia, Laudo, RevisaoLaudo
from django.contrib.auth import login
import threading
import time
from django.core.files.storage import FileSystemStorage
from django.shortcuts import get_object_or_404
import os
import base64
from django.conf import settings
from django.db import connection
from django.contrib import messages
from django.apps import apps
import random
import json
from decimal import Decimal
from datetime import timedelta
from django.db.utils import OperationalError, ProgrammingError


@login_required
def dashboard(request):
    # Se for admin/superuser, vai direto pro DB e não carrega a dashboard
    if request.user.is_superuser:
        return redirect('painel_banco')
        
    ultimo_status_sq = ExameStatus.objects.filter(
        id_exame=OuterRef('pk')
    ).order_by('-data_modificacao').values('id_status__descricao_status')[:1]

    # O Médico vê apenas os exames vinculados ao CRM dele
    medico_logado = get_object_or_404(Medico, crm=request.user.username)
    exames_base = Exame.objects.filter(id_medico=medico_logado).annotate(status_atual=Subquery(ultimo_status_sq))

    aguardando_imagem = exames_base.filter(status_atual='Aguardando Imagem').order_by('-data_hora_solicitacao')
    em_processamento = exames_base.filter(status_atual='Em Processamento IA').order_by('-data_hora_solicitacao')
    aguardando_laudo = exames_base.filter(status_atual='Aguardando Laudo').order_by('-data_hora_solicitacao')
    concluidos = exames_base.filter(status_atual='Concluído').order_by('-data_hora_solicitacao')[:10]

    context = {
        'aguardando_imagem': aguardando_imagem,
        'em_processamento': em_processamento,
        'aguardando_laudo': aguardando_laudo,
        'concluidos': concluidos,
        'medico_logado': medico_logado, 
    }

    return render(request, 'conta/dashboard.html', context)

@login_required
def buscar_paciente_api(request):
    query = request.GET.get('q', '')
    if query:
        pacientes = Paciente.objects.filter(
            Q(nome_completo__istartswith=query) | Q(cpf__startswith=query)
        )[:10]
        resultados = [{'id': p.id_paciente, 'nome': p.nome_completo, 'cpf': p.cpf} for p in pacientes]
    else:
        resultados = []
    return JsonResponse(resultados, safe=False)

# --- Telas de Cadastro ---
@login_required
def cadastro_paciente(request):
    if request.method == 'POST':
        form = PacienteForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('cadastro_exame')
    else:
        form = PacienteForm()
    
    return render(request, 'conta/cadastro_paciente.html', {'form': form})

@login_required
def cadastro_exame(request):

    medico_logado = Medico.objects.get(crm=request.user.username)   

    if request.method == 'POST':
        form = ExameForm(request.POST)
        paciente_id = request.POST.get('paciente_id_hidden')
        
        if form.is_valid() and paciente_id:
            exame = form.save(commit=False)
            exame.id_paciente = Paciente.objects.get(pk=paciente_id)
            exame.id_medico = medico_logado
            exame.data_hora_solicitacao = timezone.now()
            exame.save()


            status_inicial, _ = Status.objects.get_or_create(descricao_status='Aguardando Imagem')
            ExameStatus.objects.create(
                id_status=status_inicial,
                id_exame=exame,
                data_modificacao=timezone.now()
            )


            return redirect('dashboard') 
    else:
        form = ExameForm()

    return render(request, 'conta/cadastro_exame.html', {'form': form, 'medico_logado': medico_logado})

def criar_conta_medico(request):

    try:
        if request.method == 'POST':
            form = MedicoRegistroForm(request.POST)
            if form.is_valid():
                dados = form.cleaned_data
                
                # Verifica se já existe um usuário com esse CRM (username)
                if not User.objects.filter(username=dados['crm']).exists():
                    # Cria o controle de acesso e senha no Django
                    user = User.objects.create_user(username=dados['crm'], password=dados['senha'])
                    user.first_name = dados['nome_completo'].split()[0]
                    user.save()
                    
                    # Cria os dados médicos na sua tabela MySQL
                    Medico.objects.create(
                        nome_completo=dados['nome_completo'],
                        crm=dados['crm'],
                        uf_crm=dados['uf_crm'],
                        especialidade=dados['especialidade'],
                        email_institucional=dados['email_institucional'],
                    )
                    
                    # Faz o login automático e manda pro dashboard
                    login(request, user)
                    return redirect('dashboard')
                else:
                    form.add_error('crm', 'Já existe um cadastro com este CRM.')
        else:
            form = MedicoRegistroForm()
            
        return render(request, 'conta/criar_conta.html', {'form': form})
    except (OperationalError, ProgrammingError):
        messages.error(request, "O sistema ainda não foi inicializado. Solicite ao administrador que execute o script de criação do banco de dados (Painel Admin DB).")
        return redirect('login')

def processar_ia_background(inferencia_id, exame_id):
    inferencia = Inferencia.objects.get(pk=inferencia_id)
    imagens = ImagemMedica.objects.filter(id_inferencia=inferencia)

    imagens_b64 = []
    for img in imagens:
        nome_arquivo = img.caminho_armazenamento.split('/')[-1]
        caminho_local = os.path.join(settings.MEDIA_ROOT, nome_arquivo)

        try:
            with open(caminho_local, "rb") as f:
                imagens_b64.append(base64.b64encode(f.read()).decode('utf-8'))
        except Exception as e:
            print(f"Erro ao ler imagem {nome_arquivo}: {e}")

    url_ollama = "http://localhost:11434/api/generate"
    prompt = (
        "You are a medical AI assistant. Analyze this radiological image carefully. "
        "Describe the visible anatomical structures and point out any bone fractures, anomalies, or state if it appears normal. "
        "Be concise but thorough in your analysis."
    )

    payload = {
        "model": "moondream",
        "prompt": prompt,
        "images": imagens_b64,
        "stream": False,
        "options": {
            "temperature": 0.0, # Zero criatividade, evita alucinações
            "top_p": 0.5        # Foca nas palavras mais prováveis
        }
    }

    start_time_fallback = time.time()

    try:
        resposta = requests.post(url_ollama, json=payload)
        resposta.raise_for_status() # Verifica se a API não retornou erro 500
        dados = resposta.json()

        # Extrai os dados reais fornecidos pelo Ollama
        texto_ia = dados.get("response", "O modelo não retornou um texto válido.")
        tokens = dados.get("eval_count", 0)
        
        # O Ollama devolve o tempo em nanosegundos, convertendo para milissegundos
        tempo_ms = int(dados.get("total_duration", 0) / 1000000) 
        status_resultado = 'Sucesso'

    except Exception as e:
        # Se o Ollama estiver desligado ou der erro, registramos a falha
        texto_ia = f"Falha na comunicação com o MLLM local. Erro: {str(e)}"
        tokens = 0
        tempo_ms = int((time.time() - start_time_fallback) * 1000)
        status_resultado = 'Falha'

    inferencia.tempo_processamento = tempo_ms
    inferencia.status_resultado = status_resultado
    inferencia.save()

    Laudo.objects.create(
        data_hora_geracao=timezone.now(),
        texto_gerado=texto_ia.strip(),
        tokens_consumidos=tokens,
        prompt_utilizado=prompt,
        id_modelo=inferencia.id_modelo,
        id_inferencia=inferencia
    )

    exame = Exame.objects.get(pk=exame_id)
    status_laudo, _ = Status.objects.get_or_create(descricao_status='Aguardando Laudo')
    ExameStatus.objects.create(
        id_status=status_laudo,
        id_exame=exame,
        data_modificacao=timezone.now()
    )


# VIEW: Tela do upload
@login_required
def upload_imagens(request, exame_id):
    exame = get_object_or_404(Exame, pk=exame_id)

    if request.method == 'POST':

        form = MultiplaImagemForm(request.POST, request.FILES)

        if form.is_valid():

            imagens = request.FILES.getlist('imagens')

            if imagens:
                modelo, _ = ModeloMllm.objects.get_or_create(
                    nome_modelo='moondream', defaults={'versao': '1.8B', 'arquitetura': 'ViT+LLM'}
                )


                inferencia = Inferencia.objects.create(
                    data_hora_inicio=timezone.now(),
                    tempo_processamento=0,
                    status_resultado='Em Processamento',
                    id_modelo=modelo
                )

                # Salva todas as imagens enviadas e conecta à Inferência
                fs = FileSystemStorage()
                for img in imagens:
                    filename = fs.save(img.name, img)
                    caminho_arquivo = fs.url(filename)
                    tamanho_mb = img.size / (1024 * 1024)

                    ImagemMedica.objects.create(
                        resolucao_largura=1024,
                        resolucao_altura=1024,
                        data_hora_aquisicao=timezone.now(),
                        formato_arquivo=img.name.split('.')[-1].upper()[:10],
                        tamanho_arquivo_mb=tamanho_mb,
                        caminho_armazenamento=caminho_arquivo,
                        id_exame=exame,
                        id_inferencia=inferencia
                    )

                # Atualiza o status do exame para "Em Processamento IA"
                status_proc, _ = Status.objects.get_or_create(descricao_status='Em Processamento IA')
                ExameStatus.objects.create(
                    id_status=status_proc,
                    id_exame=exame,
                    data_modificacao=timezone.now()
                )

                # Dispara a Thread em background
                thread = threading.Thread(target=processar_ia_background, args=(inferencia.pk, exame.pk))
                thread.start()

                # Redireciona na hora, não espera a IA terminar
                return redirect('dashboard')
    else:
        form = MultiplaImagemForm()

    return render(request, 'conta/upload_imagens.html', {'form': form, 'exame': exame})

@login_required
def laudar_exame(request, exame_id):
    exame = get_object_or_404(Exame, pk=exame_id)
    medico_logado = Medico.objects.get(crm=request.user.username)
    
    # Busca todas as imagens do exame
    imagens = ImagemMedica.objects.filter(id_exame=exame)
    
    # Encontra a Inferencia e o Laudo gerado pela IA
    inferencia = imagens.first().id_inferencia if imagens.exists() else None
    laudo_ia = Laudo.objects.filter(id_inferencia=inferencia).first() if inferencia else None

    if request.method == 'POST':
        form = RevisaoLaudoForm(request.POST)
        if form.is_valid() and laudo_ia:
            # Atualiza o Laudo existente com o veredito do médico
            laudo_ia.conteudo_final = form.cleaned_data['conteudo_final']
            laudo_ia.data_hora_assinatura = timezone.now()
            laudo_ia.status_aprovacao = 'Assinado'
            laudo_ia.save()

            # Cria o registro de Revisão
            RevisaoLaudo.objects.create(
                data_hora_revisao=timezone.now(),
                concordancia=form.cleaned_data['concordancia'],
                observacao_tecnica=form.cleaned_data['observacao_tecnica'],
                id_medico=medico_logado,
                id_laudo=laudo_ia
            )

            # Atualiza o Status do Exame para "Concluído"
            status_concluido, _ = Status.objects.get_or_create(descricao_status='Concluído')
            ExameStatus.objects.create(
                id_status=status_concluido,
                id_exame=exame,
                data_modificacao=timezone.now()
            )

            return redirect('dashboard')
    else:
        initial_data = {'conteudo_final': laudo_ia.texto_gerado} if laudo_ia else {}
        form = RevisaoLaudoForm(initial=initial_data)

    context = {
        'form': form,
        'exame': exame,
        'imagens': imagens,
        'laudo_ia': laudo_ia
    }
    return render(request, 'conta/laudar_exame.html', context)

@login_required
def historico_paciente(request):
    query = request.GET.get('q', '')
    exames = []
    
    try:
        if query:
            exames = Exame.objects.filter(
                Q(id_paciente__nome_completo__icontains=query) | Q(id_paciente__cpf__icontains=query),
                examestatus__id_status__descricao_status='Concluído'
            ).distinct().order_by('-data_hora_solicitacao')
            
        return render(request, 'conta/historico_paciente.html', {'exames': exames})
            
    except (OperationalError, ProgrammingError):
        # Dispara o erro e joga de volta para a Hub
        messages.error(request, "⚠️ Acesso negado: A tabela de Exames não existe. Inicialize o banco de dados primeiro.")
        return redirect('dashboard')

@login_required
def detalhes_exame(request, exame_id):
    # Busca o exame
    exame = get_object_or_404(Exame, pk=exame_id)
    
    # Busca as imagens
    imagens = ImagemMedica.objects.filter(id_exame=exame)
    
    # Busca a Inferência e o Laudo correspondente
    inferencia = imagens.first().id_inferencia if imagens.exists() else None
    laudo = Laudo.objects.filter(id_inferencia=inferencia).first() if inferencia else None
    
    # Busca a revisão do médico (se existir)
    revisao = RevisaoLaudo.objects.filter(id_laudo=laudo).first() if laudo else None

    context = {
        'exame': exame,
        'imagens': imagens,
        'laudo': laudo,
        'revisao': revisao
    }
    
    return render(request, 'conta/detalhes_exame.html', context)

@login_required
def check_processamento_api(request):
    # Usa a mesma lógica do dashboard para saber se há algo processando
    ultimo_status_sq = ExameStatus.objects.filter(
        id_exame=OuterRef('pk')
    ).order_by('-data_modificacao').values('id_status__descricao_status')[:1]

    qtd_processando = Exame.objects.annotate(
        status_atual=Subquery(ultimo_status_sq)
    ).filter(status_atual='Em Processamento IA').count()

    # Retorna True se tiver exames processando, False se a IA já acabou tudo
    return JsonResponse({'processando': qtd_processando > 0})

def is_superuser(user):
    return user.is_superuser


@user_passes_test(is_superuser, login_url='dashboard')
def painel_banco(request):
    tabelas_logicas = [
        'Paciente', 'Medico', 'Equipamento', 'ModeloMllm', 'Status',
        'Exame', 'ExameStatus', 'ImagemMedica', 'Inferencia', 'Laudo', 'RevisaoLaudo'
    ]
    
    tabela_selecionada = request.GET.get('tabela')
    cabecalhos = []
    dados = []
    tabela_existe = True

    if tabela_selecionada and tabela_selecionada in tabelas_logicas:
        try:
            modelo = apps.get_model('conta', tabela_selecionada)
            registros = list(modelo.objects.all().values()) 
            
            if registros:
                cabecalhos = registros[0].keys()
                
                # TRATAMENTO VISUAL: Datas Brasileiras e Ocultação do "None"
                from datetime import datetime, date
                from django.utils.timezone import localtime
                
                for linha in registros:
                    for chave, valor in linha.items():
                        if isinstance(valor, datetime):
                            # Converte para o fuso horário local e formata dia/mês/ano Hora:Minuto
                            linha[chave] = localtime(valor).strftime('%d/%m/%Y %H:%M')
                        elif isinstance(valor, date):
                            # Formata apenas data
                            linha[chave] = valor.strftime('%d/%m/%Y')
                        elif valor is None:
                            # Se for nulo, mostra um travessão ao invés de "None"
                            linha[chave] = "—"
                            
                dados = registros
        except Exception as e:
            tabela_existe = False 
            messages.error(request, f"A tabela {tabela_selecionada} não existe fisicamente no banco de dados.")

    context = {
        'tabelas_logicas': tabelas_logicas,
        'tabela_selecionada': tabela_selecionada,
        'cabecalhos': cabecalhos,
        'dados': dados,
        'tabela_existe': tabela_existe,
    }
    return render(request, 'conta/painel_banco.html', context)

# --- VIEW AÇÃO: Dropar Tabelas ---
@user_passes_test(is_superuser, login_url='dashboard')
def dropar_tabelas(request):
    if request.method == 'POST':
        # Deleta os usuários criados para os médicos (preservando o superuser)
        User.objects.filter(is_superuser=False).delete()

        # Desativa a checagem de chaves estrangeiras temporariamente para dropar em lote
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
            
            # Ordem inversa das dependências
            tabelas_para_dropar = [
                'revisao_laudo', 'laudo', 'inferencia', 'imagem_medica', 
                'exame_status', 'exame', 'status', 'modelo_mllm', 
                'equipamento', 'medico', 'paciente'
            ]
            
            for tabela in tabelas_para_dropar:
                cursor.execute(f"DROP TABLE IF EXISTS {tabela};")
                
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
            
        messages.success(request, "Todas as tabelas do modelo lógico foram apagadas com sucesso! O banco está limpo.")
    
    return redirect('painel_banco')

# VIEW: Criar e Popular
@user_passes_test(is_superuser, login_url='dashboard')
def recriar_e_popular(request):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                script_sql = """
                CREATE TABLE Paciente ( ID_Paciente INTEGER AUTO_INCREMENT PRIMARY KEY, Nome_Completo VARCHAR(150) NOT NULL, CPF CHAR(14) UNIQUE NOT NULL, Data_Nascimento DATE NOT NULL, Sexo VARCHAR(15) NOT NULL, Telefone VARCHAR(20), Email VARCHAR(150));
                CREATE TABLE Equipamento ( ID_Equipamento INTEGER AUTO_INCREMENT PRIMARY KEY, Numero_Serie VARCHAR(100) UNIQUE NOT NULL, Nome_Equipamento VARCHAR(100) NOT NULL, Status_Operacional VARCHAR(30) NOT NULL, Data_Ultima_Manutencao DATE);
                CREATE TABLE Medico ( ID_Medico INTEGER AUTO_INCREMENT PRIMARY KEY, Nome_Completo VARCHAR(150) NOT NULL, CRM VARCHAR(20) UNIQUE NOT NULL, UF_CRM CHAR(2) NOT NULL, Especialidade VARCHAR(100) NOT NULL, Email_Institucional VARCHAR(150) NOT NULL);
                CREATE TABLE Status ( ID_Status INTEGER AUTO_INCREMENT PRIMARY KEY, Descricao_Status VARCHAR(50) NOT NULL);
                CREATE TABLE Modelo_MLLM ( ID_Modelo INTEGER AUTO_INCREMENT PRIMARY KEY, Nome_Modelo VARCHAR(100) NOT NULL, Versao VARCHAR(50) NOT NULL, Arquitetura VARCHAR(100) NOT NULL);
                CREATE TABLE Exame ( ID_Exame INTEGER AUTO_INCREMENT PRIMARY KEY, Data_Hora_Solicitacao TIMESTAMP NOT NULL, Regiao_Corpo VARCHAR(100) NOT NULL, Observacoes_Clinicas TEXT, ID_Equipamento INTEGER NOT NULL, ID_Paciente INTEGER NOT NULL, ID_Medico INTEGER NOT NULL);
                CREATE TABLE Exame_Status ( ID_Exame_Status INTEGER AUTO_INCREMENT PRIMARY KEY, ID_Status INTEGER NOT NULL, ID_Exame INTEGER NOT NULL, data_modificacao TIMESTAMP NOT NULL);
                CREATE TABLE Inferencia ( ID_Inferencia INTEGER AUTO_INCREMENT PRIMARY KEY, Data_Hora_Inicio TIMESTAMP NOT NULL, Tempo_Processamento INTEGER NOT NULL, Status_Resultado VARCHAR(30) NOT NULL, ID_Modelo INTEGER NOT NULL);
                CREATE TABLE Imagem_Medica ( ID_Imagem INTEGER AUTO_INCREMENT PRIMARY KEY, Resolucao_Largura INTEGER NOT NULL, Data_Hora_Aquisicao TIMESTAMP NOT NULL, Formato_Arquivo VARCHAR(10) NOT NULL, Tamanho_Arquivo_MB DECIMAL(6,2) NOT NULL, Caminho_Armazenamento VARCHAR(255) NOT NULL, Resolucao_Altura INTEGER NOT NULL, ID_Exame INTEGER NOT NULL, ID_Inferencia INTEGER NULL);
                CREATE TABLE Laudo ( ID_Laudo INTEGER AUTO_INCREMENT PRIMARY KEY, Conteudo_Final TEXT, Data_Hora_Assinatura TIMESTAMP, Status_Aprovacao VARCHAR(30), Data_Hora_Geracao TIMESTAMP NOT NULL, Texto_Gerado TEXT NOT NULL, Tokens_Consumidos INTEGER NOT NULL, Prompt_Utilizado TEXT NOT NULL, ID_Modelo INTEGER NOT NULL, ID_Inferencia INTEGER NOT NULL);
                CREATE TABLE Revisao_Laudo ( ID_Revisao INTEGER AUTO_INCREMENT PRIMARY KEY, Data_Hora_Revisao TIMESTAMP NOT NULL, Concordancia VARCHAR(20) NOT NULL, Observacao_Tecnica TEXT, ID_Medico INTEGER NOT NULL, ID_Laudo INTEGER NOT NULL);
                
                ALTER TABLE Imagem_Medica ADD CONSTRAINT FK_Imagem_Inferencia FOREIGN KEY (ID_Inferencia) REFERENCES Inferencia (ID_Inferencia) ON DELETE RESTRICT;
                ALTER TABLE Imagem_Medica ADD CONSTRAINT FK_Imagem_Medica_Exame FOREIGN KEY (ID_Exame) REFERENCES Exame (ID_Exame) ON DELETE RESTRICT;
                ALTER TABLE Exame ADD CONSTRAINT FK_Exame_Equipamento FOREIGN KEY (ID_Equipamento) REFERENCES Equipamento (ID_Equipamento) ON DELETE RESTRICT;
                ALTER TABLE Exame ADD CONSTRAINT FK_Exame_Paciente FOREIGN KEY (ID_Paciente) REFERENCES Paciente (ID_Paciente) ON DELETE RESTRICT;
                ALTER TABLE Exame ADD CONSTRAINT FK_Exame_Medico FOREIGN KEY (ID_Medico) REFERENCES Medico (ID_Medico) ON DELETE RESTRICT;
                ALTER TABLE Exame_Status ADD CONSTRAINT FK_Exame_Status_Status FOREIGN KEY (ID_Status) REFERENCES Status (ID_Status) ON DELETE RESTRICT;
                ALTER TABLE Exame_Status ADD CONSTRAINT FK_Exame_Status_Exame FOREIGN KEY (ID_Exame) REFERENCES Exame (ID_Exame) ON DELETE RESTRICT;
                ALTER TABLE Laudo ADD CONSTRAINT FK_Laudo_Modelo FOREIGN KEY (ID_Modelo) REFERENCES Modelo_MLLM (ID_Modelo) ON DELETE RESTRICT;
                ALTER TABLE Laudo ADD CONSTRAINT FK_Laudo_Inferencia FOREIGN KEY (ID_Inferencia) REFERENCES Inferencia (ID_Inferencia) ON DELETE RESTRICT;
                ALTER TABLE Revisao_Laudo ADD CONSTRAINT FK_Revisao_Laudo_Medico FOREIGN KEY (ID_Medico) REFERENCES Medico (ID_Medico) ON DELETE RESTRICT;
                ALTER TABLE Revisao_Laudo ADD CONSTRAINT FK_Revisao_Laudo_Laudo FOREIGN KEY (ID_Laudo) REFERENCES Laudo (ID_Laudo) ON DELETE RESTRICT;
                """
                comandos = [c.strip() for c in script_sql.split(';') if c.strip()]
                for cmd in comandos:
                    cursor.execute(cmd)

            agora = timezone.now()

            # 1. STATUS E MODELOS MLLM 
            for s in ['Aguardando Imagem', 'Em Processamento IA', 'Aguardando Laudo', 'Concluído']:
                Status.objects.create(descricao_status=s)
            
            StatusImg = Status.objects.get(descricao_status='Aguardando Imagem')
            StatusProc = Status.objects.get(descricao_status='Em Processamento IA')
            StatusLaud = Status.objects.get(descricao_status='Aguardando Laudo')
            StatusConc = Status.objects.get(descricao_status='Concluído')

            mod1 = ModeloMllm.objects.create(nome_modelo="moondream", versao="1.8B", arquitetura="ViT+LLM")
            mod2 = ModeloMllm.objects.create(nome_modelo="llava", versao="7B", arquitetura="ViT+LLM")
            mod3 = ModeloMllm.objects.create(nome_modelo="BakLLaVA", versao="7B", arquitetura="ViT+LLM")
            mod4 = ModeloMllm.objects.create(nome_modelo="Qwen-VL-Chat", versao="7B", arquitetura="ViT+LLM")
            lista_modelos = [mod1, mod2, mod3, mod4]

            # 2. EQUIPAMENTOS (Apenas Raio-X)
            eq1 = Equipamento.objects.create(numero_serie="RX-FIXO-001", nome_equipamento="Raio-X Digital Fixo", status_operacional="Ativo", data_ultima_manutencao=agora - timedelta(days=30))
            eq2 = Equipamento.objects.create(numero_serie="RX-PORT-002", nome_equipamento="Raio-X Portátil Móvel", status_operacional="Ativo", data_ultima_manutencao=agora - timedelta(days=15))
            eq3 = Equipamento.objects.create(numero_serie="RX-TELE-003", nome_equipamento="Raio-X Telecomandado", status_operacional="Ativo", data_ultima_manutencao=agora - timedelta(days=5))
            lista_equipamentos = [eq1, eq2, eq3]

            # 3. PACIENTES
            nomes_pac = [
                "João Silva", "Maria Costa", "Roberto Santos", "Ana Oliveira", "Carlos Lima", 
                "Fernanda Souza", "Lucas Pereira", "Juliana Alves", "Marcos Rocha", "Beatriz Mendes", 
                "Rafael Gomes", "Camila Martins", "Thiago Ribeiro", "Patrícia Dias", "Bruno Carvalho", 
                "Letícia Castro", "Felipe Nunes", "Mariana Barbosa", "Rodrigo Pinto", "Amanda Teixeira"
            ]
            lista_pacientes = []
            for nome in nomes_pac:
                cpf = f"{random.randint(100, 999)}.{random.randint(100, 999)}.{random.randint(100, 999)}-{random.randint(10, 99)}"
                paciente = Paciente.objects.create(
                    nome_completo=nome,
                    cpf=cpf,
                    data_nascimento=(agora - timedelta(days=random.randint(7000, 25000))).date(),
                    sexo=random.choice(["Masculino", "Feminino"]),
                    telefone=f"(48) 9{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                    email=f"{nome.split()[0].lower()}@email.com"
                )
                lista_pacientes.append(paciente)

            # 4. MÉDICOS
            senha_padrao = "senha"
            medicos_info = [
                {"nome": "Dr. Antonio Carlos", "crm": "111222", "esp": "Radiologia"},
                {"nome": "Dra. Laura Mendes", "crm": "333444", "esp": "Ortopedia"},
                {"nome": "Dr. Paulo Silveira", "crm": "555666", "esp": "Traumatologia"},
                {"nome": "Dra. Renata Vasconcelos", "crm": "777888", "esp": "Clínica Médica"},
                {"nome": "Dr. Fernando Diniz", "crm": "999000", "esp": "Radiologia Intervencionista"},
                {"nome": "Dra. Marcela Faria", "crm": "121212", "esp": "Ortopedia Pediátrica"},
                {"nome": "Dr. Thiago Nogueira", "crm": "343434", "esp": "Medicina Esportiva"},
                {"nome": "Dra. Carolina Guedes", "crm": "565656", "esp": "Pronto Atendimento"}
            ]
            
            lista_medicos = []
            credenciais_msg = f"<strong>Senha padrão para todos:</strong> {senha_padrao}<br><br>"
            for m in medicos_info:
                med = Medico.objects.create(nome_completo=m["nome"], crm=m["crm"], uf_crm="SC", especialidade=m["esp"], email_institucional=f"{m['crm']}@hospital.com")
                user = User.objects.create_user(username=m["crm"], password=senha_padrao)
                user.first_name = m["nome"].split()[1] 
                user.save()
                lista_medicos.append(med)
                credenciais_msg += f"Médico: {m['nome']} | Login (CRM): <strong>{m['crm']}</strong><br>"

            # 5. DADOS VARIÁVEIS PARA EXAMES E LAUDOS
            regioes = ["Tórax (PA e Perfil)", "Joelho Esquerdo", "Crânio (AP e Perfil)", "Coluna Lombar", "Mão Direita", "Pé Esquerdo", "Bacia (AP)", "Ombro Direito"]
            
            obs_clinicas_opcoes = [
                "Paciente refere dor aguda após queda da própria altura.",
                "Trauma contuso durante partida de futebol. Edema local acentuado.",
                "Acompanhamento de consolidação óssea pós-cirúrgica (30 dias).",
                "Dor crônica que piora com esforço físico. Sem histórico de trauma recente.",
                "Suspeita de fratura por estresse. Atleta amador (corrida).",
                "Quadro de dispneia e tosse persistente há 2 semanas. Investigar consolidação.",
                "Check-up ocupacional periódico. Assintomático.",
                "Dor articular matinal, limitação de amplitude. Suspeita de osteoartrite.",
                "Aumento de volume articular e calor local. Investigar possível efusão.",
                "Deformidade visível após impacto direto. Imobilização provisória colocada."
            ]

            textos_ia_fake = [
                "Estruturas ósseas íntegras. Espaços articulares preservados. Ausência de fraturas agudas ou lesões líticas evidentes.",
                "Sinais de fratura transversa na porção distal. Edema de partes moles associado nos planos adjacentes.",
                "Redução do espaço articular, esclerose subcondral e pequenos osteófitos marginais, sugerindo processo degenerativo (osteoartrose).",
                "Exame radiológico dentro dos limites da normalidade anatômica para a faixa etária. Sem achados patológicos significativos.",
                "Opacidade focal consolidativa com broncograma aéreo em permeio. Sugestivo de processo inflamatório/infeccioso agudo.",
                "Traço de fratura oblíqua sem desvio significativo dos fragmentos ósseos. Alinhamento mantido."
            ]

            revisoes_opcoes = [
                {"conc": "Concordância Total", "obs": "A inferência foi extremamente precisa. Identificou a fratura exatamente como visível na imagem."},
                {"conc": "Concordância Total", "obs": "Sem ressalvas. O modelo mapeou bem a estrutura anatômica normal do paciente."},
                {"conc": "Concordância Parcial", "obs": "A IA identificou a fratura principal, mas omitiu a presença de calcificações adjacentes. Adicionei no texto final."},
                {"conc": "Concordância Parcial", "obs": "Texto da IA estava um pouco redundante. Ajustei para o jargão técnico padrão do hospital, mas o diagnóstico estava correto."},
                {"conc": "Discordância", "obs": "O modelo indicou aspecto normal, porém ao ampliar a imagem nota-se um traço de fratura sutil não detectado pela rede neural."},
                {"conc": "Discordância", "obs": "Alucinação da IA. Relatou processo degenerativo que não está presente na radiografia atual."}
            ]

            # 6. GERAÇÃO DE EXAMES
            for i in range(1, 41):
                data_req = agora - timedelta(days=random.randint(0, 10), hours=random.randint(1, 12))
                medico = random.choice(lista_medicos)
                modelo_usado = random.choice(lista_modelos)
                texto_ia_sorteado = random.choice(textos_ia_fake)
                
                exame = Exame.objects.create(
                    data_hora_solicitacao=data_req,
                    regiao_corpo=random.choice(regioes),
                    observacoes_clinicas=random.choice(obs_clinicas_opcoes),
                    id_equipamento=random.choice(lista_equipamentos),
                    id_paciente=random.choice(lista_pacientes),
                    id_medico=medico
                )

                if i <= 10:
                    # Fila: Aguardando Imagem (Não tem inferência nem laudo)
                    ExameStatus.objects.create(id_status=StatusImg, id_exame=exame, data_modificacao=data_req)
                
                elif i <= 25:
                    # Fila: Aguardando Laudo Médico (A IA já terminou de processar com sucesso)
                    ExameStatus.objects.create(id_status=StatusLaud, id_exame=exame, data_modificacao=data_req + timedelta(minutes=15))
                    inf = Inferencia.objects.create(data_hora_inicio=data_req + timedelta(minutes=5), tempo_processamento=random.randint(8000, 25000), status_resultado='Sucesso', id_modelo=modelo_usado)
                    ImagemMedica.objects.create(resolucao_largura=1024, resolucao_altura=1024, data_hora_aquisicao=data_req + timedelta(minutes=4), formato_arquivo="JPG", tamanho_arquivo_mb=random.uniform(1.2, 3.5), caminho_armazenamento="/media/demo.jpg", id_exame=exame, id_inferencia=inf)
                    
                    # Rascunho da IA aguardando o médico
                    Laudo.objects.create(data_hora_geracao=data_req + timedelta(minutes=15), texto_gerado=texto_ia_sorteado, conteudo_final=f"[RASCUNHO NÃO ASSINADO]\n{texto_ia_sorteado}", status_aprovacao='Pendente', tokens_consumidos=random.randint(110, 180), prompt_utilizado="You are a medical AI assistant. Analyze this radiological image...", id_modelo=modelo_usado, id_inferencia=inf)

                else:
                    # Fila: Concluído (Médico revisou e assinou)
                    ExameStatus.objects.create(id_status=StatusConc, id_exame=exame, data_modificacao=data_req + timedelta(hours=2))
                    inf = Inferencia.objects.create(data_hora_inicio=data_req + timedelta(minutes=5), tempo_processamento=random.randint(8000, 25000), status_resultado='Sucesso', id_modelo=modelo_usado)
                    ImagemMedica.objects.create(resolucao_largura=1024, resolucao_altura=1024, data_hora_aquisicao=data_req + timedelta(minutes=4), formato_arquivo="DICOM", tamanho_arquivo_mb=random.uniform(5.0, 15.0), caminho_armazenamento="/media/demo.jpg", id_exame=exame, id_inferencia=inf)
                    
                    revisao_sorteada = random.choice(revisoes_opcoes)
                    
                    if revisao_sorteada["conc"] in ["Discordância", "Concordância Parcial"]:
                        texto_medico = texto_ia_sorteado + " \n\n[ADENDO MÉDICO]: Laudo corrigido manualmente após avaliação humana complementar."
                    else:
                        texto_medico = texto_ia_sorteado
                        
                    laudo = Laudo.objects.create(data_hora_geracao=data_req + timedelta(minutes=15), texto_gerado=texto_ia_sorteado, conteudo_final=texto_medico, data_hora_assinatura=data_req + timedelta(hours=2), status_aprovacao='Assinado', tokens_consumidos=random.randint(110, 180), prompt_utilizado="You are a medical AI assistant. Analyze this radiological image...", id_modelo=modelo_usado, id_inferencia=inf)
                    RevisaoLaudo.objects.create(data_hora_revisao=data_req + timedelta(hours=2), concordancia=revisao_sorteada["conc"], observacao_tecnica=revisao_sorteada["obs"], id_medico=medico, id_laudo=laudo)

            messages.success(request, f"O Banco de Dados foi populado com sucesso! Modelos MLLM (Moondream, LLaVA, BakLLaVA e Qwen-VL) aplicados em Raio-X.<br><hr>{credenciais_msg}", extra_tags='safe')

        except Exception as e:
            messages.error(request, f"Erro estrutural ao criar/popular tabelas: {e}")

    return redirect('painel_banco')

def dictfetchall(cursor):
    """Retorna todas as linhas de um cursor SQL como um dicionário Python."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

# Classe tradutora para o JSON entender os números do Banco de Dados
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

@login_required
def consultas_relatorios(request):
    try:
        with connection.cursor() as cursor:
            query1 = """
                SELECT 
                    m.Nome_Modelo, 
                    COUNT(i.ID_Inferencia) as Total_Inferencias, 
                    ROUND(AVG(i.Tempo_Processamento), 0) as Tempo_Medio_MS,
                    ROUND(AVG(l.Tokens_Consumidos), 0) as Media_Tokens
                FROM modelo_mllm m
                JOIN inferencia i ON m.ID_Modelo = i.ID_Modelo
                JOIN laudo l ON i.ID_Inferencia = l.ID_Inferencia
                GROUP BY m.Nome_Modelo;
            """
            cursor.execute(query1)
            dados_q1 = dictfetchall(cursor)

            query2 = """
                SELECT 
                    eq.Nome_Equipamento, 
                    COUNT(DISTINCT ex.ID_Exame) as Total_Exames, 
                    ROUND(SUM(im.Tamanho_Arquivo_MB), 2) as Volume_Total_MB
                FROM equipamento eq
                JOIN exame ex ON eq.ID_Equipamento = ex.ID_Equipamento
                JOIN imagem_medica im ON ex.ID_Exame = im.ID_Exame
                GROUP BY eq.Nome_Equipamento;
            """
            cursor.execute(query2)
            dados_q2 = dictfetchall(cursor)

            query3 = """
                SELECT 
                    rl.Concordancia, 
                    COUNT(rl.ID_Revisao) as Quantidade_Revisoes,
                    ROUND(AVG(l.Tokens_Consumidos), 0) as Media_Tokens_Gastos
                FROM revisao_laudo rl
                JOIN medico m ON rl.ID_Medico = m.ID_Medico
                JOIN laudo l ON rl.ID_Laudo = l.ID_Laudo
                GROUP BY rl.Concordancia
                ORDER BY Quantidade_Revisoes DESC;
            """
            cursor.execute(query3)
            dados_q3 = dictfetchall(cursor)

        context = {
            'dados_q1': dados_q1,
            'dados_q2': dados_q2,
            'dados_q3': dados_q3,
            'json_q1': json.dumps(dados_q1, cls=DecimalEncoder),
            'json_q2': json.dumps(dados_q2, cls=DecimalEncoder),
            'json_q3': json.dumps(dados_q3, cls=DecimalEncoder),
            'query1_sql': query1.strip(),
            'query2_sql': query2.strip(),
            'query3_sql': query3.strip(),
        }
        
        return render(request, 'conta/consultas.html', context)

    except (OperationalError, ProgrammingError):
        # Dispara o erro e joga de volta para a Hub
        messages.error(request, "⚠️ Acesso negado: As tabelas necessárias para os relatórios não existem. Crie as tabelas lógicas antes de acessar esta tela.")
        return redirect('dashboard')
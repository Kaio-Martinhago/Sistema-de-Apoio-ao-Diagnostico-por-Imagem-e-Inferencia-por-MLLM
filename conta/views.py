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
from datetime import timedelta


@login_required
def dashboard(request):

    
    ultimo_status_sq = ExameStatus.objects.filter(
        id_exame=OuterRef('pk')
    ).order_by('-data_modificacao').values('id_status__descricao_status')[:1]

    # 3. FILTRO PRINCIPAL: Pega TODOS os exames, MAS FILTRA APENAS OS DESTE MÉDICO

    if request.user.is_superuser:
        medico_logado = None
        # O Admin (você) vê a carga de trabalho do hospital inteiro
        exames_base = Exame.objects.all().annotate(status_atual=Subquery(ultimo_status_sq))
    else:
        # O Médico vê apenas os exames vinculados ao CRM dele
        medico_logado = get_object_or_404(Medico, crm=request.user.username)
        exames_base = Exame.objects.filter(id_medico=medico_logado).annotate(status_atual=Subquery(ultimo_status_sq))


    exames_base = Exame.objects.filter(id_medico=medico_logado).annotate(status_atual=Subquery(ultimo_status_sq))

    # 4. Distribui os exames filtrados nas "caixas" da Hub
    aguardando_imagem = exames_base.filter(status_atual='Aguardando Imagem').order_by('-data_hora_solicitacao')
    em_processamento = exames_base.filter(status_atual='Em Processamento IA').order_by('-data_hora_solicitacao')
    aguardando_laudo = exames_base.filter(status_atual='Aguardando Laudo').order_by('-data_hora_solicitacao')
    concluidos = exames_base.filter(status_atual='Concluído').order_by('-data_hora_solicitacao')[:10]

    context = {
        'aguardando_imagem': aguardando_imagem,
        'em_processamento': em_processamento,
        'aguardando_laudo': aguardando_laudo,
        'concluidos': concluidos,
        'medico_logado': medico_logado, # Passando para a tela para saudações, se quiser usar
    }

    return render(request, 'conta/dashboard.html', context)

@login_required
def buscar_paciente_api(request):
    query = request.GET.get('q', '')
    if query:
        # Busca por nome OU cpf, limitando a 10 resultados para não travar a tela
        #pacientes = Paciente.objects.filter(
        #    Q(nome_completo__icontains=query) | Q(cpf__icontains=query)
        #)[:10]
        # Agora busca apenas nomes ou CPFs que COMEÇAM com o que foi digitado
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
            return redirect('cadastro_exame') # Cadastrou? Vai direto para solicitar o exame
    else:
        form = PacienteForm()
    
    return render(request, 'conta/cadastro_paciente.html', {'form': form})

@login_required
def cadastro_exame(request):

    medico_logado = Medico.objects.get(crm=request.user.username)   

    if request.method == 'POST':
        form = ExameForm(request.POST)
        paciente_id = request.POST.get('paciente_id_hidden') # Pega o ID que o JS escondeu
        
        if form.is_valid() and paciente_id:
            exame = form.save(commit=False) # Prepara para salvar, mas não salva ainda
            exame.id_paciente = Paciente.objects.get(pk=paciente_id)
            exame.id_medico = medico_logado
            exame.data_hora_solicitacao = timezone.now()
            exame.save() # Agora salva no banco


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
    if request.method == 'POST':
        form = MedicoRegistroForm(request.POST)
        if form.is_valid():
            dados = form.cleaned_data
            
            # Verifica se já existe um usuário com esse CRM (username)
            if not User.objects.filter(username=dados['crm']).exists():
                # 1. Cria o controle de acesso e senha no Django
                user = User.objects.create_user(username=dados['crm'], password=dados['senha'])
                user.first_name = dados['nome_completo'].split()[0]
                user.save()
                
                # 2. Cria os dados médicos na sua tabela MySQL
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


def processar_ia_background(inferencia_id, exame_id):
    inferencia = Inferencia.objects.get(pk=inferencia_id)
    imagens = ImagemMedica.objects.filter(id_inferencia=inferencia)

    imagens_b64 = []
    for img in imagens:
        # Extrai o nome do arquivo a partir da URL (/media/nome_arquivo.png)
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


# --- VIEW: TELA DE UPLOAD ---
@login_required
def upload_imagens(request, exame_id):
    exame = get_object_or_404(Exame, pk=exame_id)

    if request.method == 'POST':

        form = MultiplaImagemForm(request.POST, request.FILES)

        if form.is_valid():

            imagens = request.FILES.getlist('imagens')

            if imagens:
                modelo, _ = ModeloMllm.objects.get_or_create(
                    nome_modelo='minicpm-v', defaults={'versao': '7B', 'arquitetura': 'ViT+LLM'}
                )


                inferencia = Inferencia.objects.create(
                    data_hora_inicio=timezone.now(),
                    tempo_processamento=0,
                    status_resultado='Em Processamento',
                    id_modelo=modelo
                )

                # 3. Salva todas as imagens enviadas e conecta à Inferência!
                fs = FileSystemStorage()
                for img in imagens:
                    filename = fs.save(img.name, img)
                    caminho_arquivo = fs.url(filename)
                    tamanho_mb = img.size / (1024 * 1024)

                    ImagemMedica.objects.create(
                        resolucao_largura=1024, # Poderia extrair com lib Pillow
                        resolucao_altura=1024,
                        data_hora_aquisicao=timezone.now(),
                        formato_arquivo=img.name.split('.')[-1].upper()[:10],
                        tamanho_arquivo_mb=tamanho_mb,
                        caminho_armazenamento=caminho_arquivo,
                        id_exame=exame,
                        id_inferencia=inferencia # Conecta a imagem à inferência única!
                    )

                # 4. Atualiza o status do exame para "Em Processamento IA"
                status_proc, _ = Status.objects.get_or_create(descricao_status='Em Processamento IA')
                ExameStatus.objects.create(
                    id_status=status_proc,
                    id_exame=exame,
                    data_modificacao=timezone.now()
                )

                # 5. O PULO DO GATO: Dispara a Thread em background!
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
    
    # 1. Busca todas as imagens do exame
    imagens = ImagemMedica.objects.filter(id_exame=exame)
    
    # 2. Encontra a Inferencia e o Laudo gerado pela IA
    # Como definimos que 1 inferencia tem várias imagens, podemos pegar a inferencia da 1ª imagem
    inferencia = imagens.first().id_inferencia if imagens.exists() else None
    laudo_ia = Laudo.objects.filter(id_inferencia=inferencia).first() if inferencia else None

    if request.method == 'POST':
        form = RevisaoLaudoForm(request.POST)
        if form.is_valid() and laudo_ia:
            # A) Atualiza o Laudo existente com o veredito do médico
            laudo_ia.conteudo_final = form.cleaned_data['conteudo_final']
            laudo_ia.data_hora_assinatura = timezone.now()
            laudo_ia.status_aprovacao = 'Assinado'
            laudo_ia.save()

            # B) Cria o registro de Revisão (Auditoria)
            RevisaoLaudo.objects.create(
                data_hora_revisao=timezone.now(),
                concordancia=form.cleaned_data['concordancia'],
                observacao_tecnica=form.cleaned_data['observacao_tecnica'],
                id_medico=medico_logado,
                id_laudo=laudo_ia
            )

            # C) Atualiza o Status do Exame para "Concluído"
            status_concluido, _ = Status.objects.get_or_create(descricao_status='Concluído')
            ExameStatus.objects.create(
                id_status=status_concluido,
                id_exame=exame,
                data_modificacao=timezone.now()
            )

            return redirect('dashboard')
    else:
        # Pulo do gato: Preenchemos o campo 'conteudo_final' com o que a IA gerou
        # para que o médico só precise editar em vez de digitar tudo do zero!
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
    if query:
        # Busca exames do paciente pesquisado que já têm o status "Concluído"
        exames = Exame.objects.filter(
            Q(id_paciente__nome_completo__icontains=query) | Q(id_paciente__cpf__icontains=query),
            examestatus__id_status__descricao_status='Concluído'
        ).distinct().order_by('-data_hora_solicitacao')
    
    return render(request, 'conta/historico_paciente.html', {'exames': exames})

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

    # Se o usuário clicou em uma tabela, buscamos os dados dela
    if tabela_selecionada and tabela_selecionada in tabelas_logicas:
        try:
            # Pega o modelo do Django dinamicamente pelo nome
            modelo = apps.get_model('conta', tabela_selecionada)
            
            # Pega todos os registros como um dicionário
            registros = modelo.objects.all().values()
            
            if registros.exists():
                cabecalhos = registros[0].keys()
                dados = registros
        except Exception as e:
            messages.error(request, f"Erro ao buscar dados ou tabela inexistente: {e}")

    context = {
        'tabelas_logicas': tabelas_logicas,
        'tabela_selecionada': tabela_selecionada,
        'cabecalhos': cabecalhos,
        'dados': dados,
    }
    return render(request, 'conta/painel_banco.html', context)

# --- VIEW AÇÃO: Dropar Tabelas ---
@user_passes_test(is_superuser, login_url='dashboard')
def dropar_tabelas(request):
    if request.method == 'POST':
        # Deleta os usuários criados para os médicos (preservando você, o superuser)
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

# --- VIEW AÇÃO: Criar e Popular ---
@user_passes_test(is_superuser, login_url='dashboard')
def recriar_e_popular(request):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                # O script SQL exato que você me passou (com a correção do Telefone do Medico e FKs)
                script_sql = """
                CREATE TABLE Paciente ( ID_Paciente INTEGER AUTO_INCREMENT PRIMARY KEY, Nome_Completo VARCHAR(150) NOT NULL, CPF CHAR(11) UNIQUE NOT NULL, Data_Nascimento DATE NOT NULL, Sexo VARCHAR(15) NOT NULL, Telefone VARCHAR(20), Email VARCHAR(150));
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
                # Separa os comandos por ; e executa um a um
                comandos = [c.strip() for c in script_sql.split(';') if c.strip()]
                for cmd in comandos:
                    cursor.execute(cmd)

            # --- POPULANDO DADOS BÁSICOS (Status, Equipamentos, Modelos) ---
            for s in ['Aguardando Imagem', 'Em Processamento IA', 'Aguardando Laudo', 'Concluído']:
                Status.objects.create(descricao_status=s)
            
            ModeloMllm.objects.create(nome_modelo="Moondream", versao="1.8B", arquitetura="CNN+Transformer")
            Equipamento.objects.create(numero_serie="RX-DEMO", nome_equipamento="Raio-X Digital", status_operacional="Ativo", data_ultima_manutencao=timezone.now())

            # --- POPULANDO MÉDICOS E SEUS ACESSOS NO DJANGO ---
            senha_padrao = "senha"
            medicos_info = [
                {"nome": "Dr. Antonio Carlos", "crm": "111222", "esp": "Radiologia"},
                {"nome": "Dra. Laura Mendes", "crm": "333444", "esp": "Ortopedia"}
            ]
            
            # String para exibir na tela de sucesso
            credenciais_msg = f"<strong>Senha padrão para todos os médicos:</strong> {senha_padrao}<br><br>"

            for m in medicos_info:
                # Cria no MySQL
                Medico.objects.create(nome_completo=m["nome"], crm=m["crm"], uf_crm="SC", especialidade=m["esp"], email_institucional=f"{m['crm']}@hospital.com")
                # Cria acesso no Django
                User.objects.create_user(username=m["crm"], password=senha_padrao)
                credenciais_msg += f"Médico: {m['nome']} | Login (CRM): <strong>{m['crm']}</strong><br>"

            # O Django exibe essa mensagem renderizando HTML na tela
            messages.success(request, f"Tabelas recriadas e populadas com sucesso!<br><hr>{credenciais_msg}", extra_tags='safe')

        except Exception as e:
            messages.error(request, f"Erro ao criar/popular tabelas: {e}")

    return redirect('painel_banco')
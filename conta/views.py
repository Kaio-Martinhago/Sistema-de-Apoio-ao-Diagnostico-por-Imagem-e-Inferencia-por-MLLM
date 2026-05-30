from django.db.models import Count, OuterRef, Subquery
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
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

@login_required
def dashboard(request):
    # 1. Subquery: Busca a descrição do status mais recente (data_modificacao) para cada exame
    ultimo_status_sq = ExameStatus.objects.filter(
        id_exame=OuterRef('pk')
    ).order_by('-data_modificacao').values('id_status__descricao_status')[:1]

    # 2. Anota cada Exame com seu status atual baseado na subquery acima
    exames_com_status = Exame.objects.annotate(status_atual=Subquery(ultimo_status_sq))

    # 3. Filtra os exames para as diferentes "caixas" de trabalho do médico
    # Mostramos os exames do mais recente para o mais antigo
    aguardando_imagem = exames_com_status.filter(status_atual='Aguardando Imagem').order_by('-data_hora_solicitacao')
    em_processamento = exames_com_status.filter(status_atual='Em Processamento IA').order_by('-data_hora_solicitacao')
    aguardando_laudo = exames_com_status.filter(status_atual='Aguardando Laudo').order_by('-data_hora_solicitacao')
    concluidos = exames_com_status.filter(status_atual='Concluído').order_by('-data_hora_solicitacao')[:10] # Limita a 10 para não lotar a tela

    context = {
        'aguardando_imagem': aguardando_imagem,
        'em_processamento': em_processamento,
        'aguardando_laudo': aguardando_laudo,
        'concluidos': concluidos,
    }

    return render(request, 'conta/dashboard.html', context)

@login_required
def buscar_paciente_api(request):
    query = request.GET.get('q', '')
    if query:
        # Busca por nome OU cpf, limitando a 10 resultados para não travar a tela
        pacientes = Paciente.objects.filter(
            Q(nome_completo__icontains=query) | Q(cpf__icontains=query)
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
                    nome_modelo='Moondream', defaults={'versao': '1.8B', 'arquitetura': 'CNN+Transformer'}
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
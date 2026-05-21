from django.db.models import Count
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Q
from django.utils import timezone
from .forms import PacienteForm, ExameForm
from .models import Paciente, Medico, Equipamento, Exame, ModeloMllm


@login_required
def dashboard(request):
    # 1. KPIs (Cards principais)
    total_pacientes = Paciente.objects.count()
    total_exames = Exame.objects.count()
    equipamentos_ativos = Equipamento.objects.filter(status_operacional='Ativo').count()
    total_medicos = Medico.objects.count()

    # 2. Últimos 5 Exames (Usando select_related para otimizar a query com as chaves estrangeiras)
    ultimos_exames = Exame.objects.select_related('id_paciente', 'id_medico', 'id_equipamento').order_by('-data_hora_solicitacao')[:5]

    # 3. Listas para tabelas auxiliares
    lista_medicos = Medico.objects.all()
    lista_modelos = ModeloMllm.objects.all()

    # 4. Dados para o Gráfico (Exames realizados por equipamento)
    # Conta quantos exames cada equipamento fez
    exames_por_equipamento = Equipamento.objects.annotate(total_exames=Count('exame')).values('nome_equipamento', 'numero_serie', 'total_exames')

    # Empacota tudo para enviar ao HTML
    context = {
        'total_pacientes': total_pacientes,
        'total_exames': total_exames,
        'equipamentos_ativos': equipamentos_ativos,
        'total_medicos': total_medicos,
        'ultimos_exames': ultimos_exames,
        'lista_medicos': lista_medicos,
        'lista_modelos': lista_modelos,
        # O list() é necessário para o Javascript conseguir ler os dados depois
        'exames_por_equipamento': list(exames_por_equipamento), 
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
    if request.method == 'POST':
        form = ExameForm(request.POST)
        paciente_id = request.POST.get('paciente_id_hidden') # Pega o ID que o JS escondeu
        
        if form.is_valid() and paciente_id:
            exame = form.save(commit=False) # Prepara para salvar, mas não salva ainda
            exame.id_paciente = Paciente.objects.get(pk=paciente_id)
            exame.data_hora_solicitacao = timezone.now()
            exame.save() # Agora salva no banco
            return redirect('dashboard') # Retorna ao dashboard (depois mudaremos para a tela de upload)
    else:
        form = ExameForm()

    return render(request, 'conta/cadastro_exame.html', {'form': form})
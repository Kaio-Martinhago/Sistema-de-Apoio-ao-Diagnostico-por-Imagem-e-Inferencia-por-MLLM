from django import forms
from .models import Paciente, Exame, Medico, Equipamento

class PacienteForm(forms.ModelForm):
    class Meta:
        model = Paciente
        fields = ['nome_completo', 'cpf', 'data_nascimento', 'sexo', 'telefone', 'email']
        widgets = {
            'data_nascimento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'nome_completo': forms.TextInput(attrs={'class': 'form-control'}),
            'cpf': forms.TextInput(attrs={'class': 'form-control'}),
            'sexo': forms.Select(choices=[('Masculino', 'Masculino'), ('Feminino', 'Feminino'), ('Outro', 'Outro')], attrs={'class': 'form-select'}),
            'telefone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

class ExameForm(forms.ModelForm):
    class Meta:
        model = Exame
        # Não incluímos id_paciente e data_hora aqui, pois preencheremos na view
        fields = ['regiao_corpo', 'id_equipamento', 'observacoes_clinicas']
        widgets = {
            'regiao_corpo': forms.TextInput(attrs={'class': 'form-control'}),
            'id_equipamento': forms.Select(attrs={'class': 'form-select'}),
            'observacoes_clinicas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['id_equipamento'].queryset = Equipamento.objects.filter(status_operacional='Ativo')
            self.fields['id_equipamento'].empty_label = "Selecione um equipamento..."

class MedicoRegistroForm(forms.Form):
    nome_completo = forms.CharField(max_length=150, widget=forms.TextInput(attrs={'class': 'form-control'}))
    crm = forms.CharField(max_length=20, widget=forms.TextInput(attrs={'class': 'form-control'}))
    uf_crm = forms.CharField(max_length=2, widget=forms.TextInput(attrs={'class': 'form-control'}))
    especialidade = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email_institucional = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    senha = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
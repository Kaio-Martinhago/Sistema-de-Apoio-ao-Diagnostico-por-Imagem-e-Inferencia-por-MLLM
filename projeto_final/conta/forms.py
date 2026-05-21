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
        fields = ['regiao_corpo', 'id_medico', 'id_equipamento', 'observacoes_clinicas']
        widgets = {
            'regiao_corpo': forms.TextInput(attrs={'class': 'form-control'}),
            'id_medico': forms.Select(attrs={'class': 'form-select'}),
            'id_equipamento': forms.Select(attrs={'class': 'form-select'}),
            'observacoes_clinicas': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
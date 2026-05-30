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

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = [single_file_clean(data, initial)]
        return result

class MultiplaImagemForm(forms.Form):
    imagens = MultipleFileField(
        label='Selecione as imagens do exame (PNG ou JPEG)',
        widget=MultipleFileInput(attrs={
            'class': 'form-control', 
            'accept': 'image/png, image/jpeg'
        })
    )


class RevisaoLaudoForm(forms.Form):
    conteudo_final = forms.CharField(
        label="Laudo Definitivo",
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 8, 'placeholder': 'Edite ou valide o texto gerado pela IA aqui...'})
    )
    concordancia = forms.ChoiceField(
        label="Concordância com o modelo de IA",
        choices=[('Total', 'Total'), ('Parcial', 'Parcial'), ('Discordante', 'Discordante')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    observacao_tecnica = forms.CharField(
        label="Observações Técnicas / Feedback (Opcional)",
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'O modelo acertou a região, mas errou a gravidade...'})
    )

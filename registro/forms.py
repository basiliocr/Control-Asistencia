from django import forms
from django.contrib.auth.models import User

from .models import Pasante, Asistencia, DiaEspecial


class PasanteForm(forms.ModelForm):
    username = forms.CharField(label="Usuario (para iniciar sesión)", max_length=150)
    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Al editar, deja este campo vacío para conservar la contraseña actual.",
    )

    class Meta:
        model = Pasante
        fields = [
            "nombre",
            "ci",
            "area",
            "identificador",
            "horario_entrada",
            "horario_salida",
            "activo",
        ]
        widgets = {
            "horario_entrada": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "horario_salida": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["username"].initial = self.instance.user.username

    def clean_username(self):
        username = self.cleaned_data["username"]
        qs = User.objects.filter(username=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError("Ya existe un usuario con ese nombre.")
        return username


class AsistenciaForm(forms.ModelForm):
    class Meta:
        model = Asistencia
        fields = ["hora_entrada", "hora_salida", "tardanza_min", "estado"]
        widgets = {
            "hora_entrada": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "hora_salida": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }


class DiaEspecialForm(forms.ModelForm):
    class Meta:
        model = DiaEspecial
        fields = ["fecha", "tipo", "hora_entrada_especial", "descripcion"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "hora_entrada_especial": forms.TimeInput(
                attrs={"type": "time"}, format="%H:%M"
            ),
        }

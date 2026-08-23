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


class AdminUserForm(forms.ModelForm):
    """Crear o editar una cuenta de administrador (staff)."""

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Al editar, deja este campo vacío para conservar la contraseña actual.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "is_superuser", "is_active"]
        labels = {
            "username": "Usuario",
            "first_name": "Nombre a mostrar",
            "is_superuser": "Superusuario (control total del sistema)",
            "is_active": "Cuenta activa",
        }

    def clean_username(self):
        username = self.cleaned_data["username"]
        qs = User.objects.filter(username=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un usuario con ese nombre.")
        return username


from django.contrib.auth.forms import AuthenticationForm
from .models import LoginSecurity


class LoginConBloqueoForm(AuthenticationForm):
    """Login que rechaza el acceso si la cuenta está bloqueada por intentos fallidos."""

    def clean(self):
        username = self.cleaned_data.get("username")
        if username:
            try:
                user = User.objects.get(username=username)
                sec, _ = LoginSecurity.objects.get_or_create(usuario=user)
                if sec.esta_bloqueado():
                    segs = sec.segundos_restantes()
                    raise forms.ValidationError(
                        f"Cuenta bloqueada por seguridad tras varios intentos fallidos. "
                        f"Intenta de nuevo en {segs} segundos."
                    )
            except User.DoesNotExist:
                pass
        return super().clean()

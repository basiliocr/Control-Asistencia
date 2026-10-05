from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

from .models import (
    Pasante,
    Asistencia,
    DiaEspecial,
    LoginSecurity,
    IPSecurity,
    obtener_ip,
)
from .services import verificar_o_vincular_dispositivo


class PasanteForm(forms.ModelForm):
    username = forms.CharField(
        label="Usuario (para iniciar sesión)",
        max_length=150,
    )

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text=(
            "Al editar, deja este campo vacío para conservar " "la contraseña actual."
        ),
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
            "horario_entrada": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
            "horario_salida": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
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
        fields = [
            "hora_entrada",
            "hora_salida",
            "estado",
        ]
        widgets = {
            "hora_entrada": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
            "hora_salida": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
        }


class DiaEspecialForm(forms.ModelForm):
    class Meta:
        model = DiaEspecial
        fields = [
            "fecha",
            "tipo",
            "hora_entrada_especial",
            "descripcion",
        ]
        widgets = {
            "fecha": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "hora_entrada_especial": forms.TimeInput(
                attrs={"type": "time"},
                format="%H:%M",
            ),
        }


class AdminUserForm(forms.ModelForm):
    """
    Crear o editar una cuenta de administrador (staff).
    """

    password = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text=(
            "Al editar, deja este campo vacío para conservar " "la contraseña actual."
        ),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "first_name",
            "is_superuser",
            "is_active",
        ]
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


class LoginConBloqueoForm(AuthenticationForm):
    """
    Formulario de inicio de sesión con:

    1. Bloqueo temporal por intentos fallidos de la cuenta.
    2. Bloqueo temporal por IP.
    3. Vinculación del dispositivo del pasante.
    """

    def clean(self):
        username = self.cleaned_data.get("username")

        # ---------------------------------------------------------
        # 1. COMPROBAR BLOQUEO POR IP
        # ---------------------------------------------------------
        if self.request is not None:
            ip = obtener_ip(self.request)

            if ip:
                sec_ip = IPSecurity.objects.filter(ip=ip).first()

                if sec_ip and sec_ip.esta_bloqueado():
                    segundos = sec_ip.segundos_restantes()

                    raise forms.ValidationError(
                        f"Demasiados intentos fallidos desde esta red. "
                        f"Intenta de nuevo en {segundos} segundos."
                    )

        # ---------------------------------------------------------
        # 2. COMPROBAR BLOQUEO DE LA CUENTA
        # ---------------------------------------------------------
        if username:
            try:
                user = User.objects.get(username=username)

                sec, _ = LoginSecurity.objects.get_or_create(usuario=user)

                if sec.esta_bloqueado():
                    segundos = sec.segundos_restantes()

                    raise forms.ValidationError(
                        "Cuenta bloqueada por seguridad tras varios "
                        "intentos fallidos. "
                        f"Intenta de nuevo en {segundos} segundos."
                    )

            except User.DoesNotExist:
                # No revelamos si el usuario existe o no.
                pass

        # ---------------------------------------------------------
        # 3. AUTENTICACIÓN NORMAL DE DJANGO
        # ---------------------------------------------------------
        cleaned = super().clean()

        user = self.get_user()

        # ---------------------------------------------------------
        # 4. VERIFICAR / VINCULAR DISPOSITIVO DEL PASANTE
        # ---------------------------------------------------------
        if user and hasattr(user, "pasante"):
            dispositivo = self.data.get("dispositivo")

            ok, error = verificar_o_vincular_dispositivo(
                user.pasante,
                dispositivo,
            )

            if not ok:
                raise forms.ValidationError(error)

        return cleaned


class RangoDiaEspecialForm(forms.Form):
    """
    Para crear uno o varios días especiales
    (feriados que duran varios días).
    """

    fecha_desde = forms.DateField(
        label="Desde",
        widget=forms.DateInput(
            attrs={"type": "date"},
            format="%Y-%m-%d",
        ),
    )

    fecha_hasta = forms.DateField(
        label="Hasta (opcional; déjalo vacío si es un solo día)",
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date"},
            format="%Y-%m-%d",
        ),
    )

    tipo = forms.ChoiceField(
        label="Tipo",
        choices=DiaEspecial.TIPOS,
    )

    hora_entrada_especial = forms.TimeField(
        label="Hora de entrada especial " "(solo si es horario especial)",
        required=False,
        widget=forms.TimeInput(
            attrs={"type": "time"},
            format="%H:%M",
        ),
    )

    descripcion = forms.CharField(
        label="Descripción",
        required=False,
        max_length=200,
    )

    def clean(self):
        cleaned = super().clean()

        fecha_desde = cleaned.get("fecha_desde")
        fecha_hasta = cleaned.get("fecha_hasta")

        if fecha_desde and fecha_hasta and fecha_hasta < fecha_desde:
            self.add_error(
                "fecha_hasta",
                "La fecha final no puede ser anterior " "a la fecha inicial.",
            )

        return cleaned

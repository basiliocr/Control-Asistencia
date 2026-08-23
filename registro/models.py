from django.db import models
from django.contrib.auth.models import User


class Pasante(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="pasante")
    nombre = models.CharField(max_length=120)
    ci = models.CharField(max_length=20, unique=True)
    area = models.CharField(max_length=80)
    identificador = models.CharField(max_length=20, unique=True)
    horario_entrada = models.TimeField()
    horario_salida = models.TimeField()
    activo = models.BooleanField(default=True)
    dispositivo_id = models.CharField(max_length=64, blank=True, default="")

    def __str__(self):
        return f"{self.identificador} - {self.nombre}"


class Asistencia(models.Model):
    ESTADO_COMPLETO = "completo"
    ESTADO_SIN_SALIDA = "entrada_sin_salida"
    ESTADO_CORREGIDO = "corregido"
    ESTADOS = [
        (ESTADO_COMPLETO, "Completo"),
        (ESTADO_SIN_SALIDA, "Entrada sin salida"),
        (ESTADO_CORREGIDO, "Corregido"),
    ]

    pasante = models.ForeignKey(
        Pasante, on_delete=models.PROTECT, related_name="asistencias"
    )
    fecha = models.DateField()
    hora_entrada = models.TimeField(null=True, blank=True)
    hora_salida = models.TimeField(null=True, blank=True)
    tardanza_min = models.PositiveIntegerField(default=0)
    estado = models.CharField(max_length=20, choices=ESTADOS, default=ESTADO_SIN_SALIDA)
    lat_entrada = models.FloatField(null=True, blank=True)
    lng_entrada = models.FloatField(null=True, blank=True)
    lat_salida = models.FloatField(null=True, blank=True)
    lng_salida = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = ("pasante", "fecha")
        ordering = ["-fecha", "pasante"]

    def __str__(self):
        return f"{self.pasante.identificador} {self.fecha}"


class Correccion(models.Model):
    asistencia = models.ForeignKey(
        Asistencia, on_delete=models.CASCADE, related_name="correcciones"
    )
    admin = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="correcciones"
    )
    fecha_hora = models.DateTimeField(auto_now_add=True)
    detalle = models.TextField()

    def __str__(self):
        return f"Corrección de asistencia #{self.asistencia_id} por {self.admin}"


class DiaEspecial(models.Model):
    FERIADO = "feriado"
    HORARIO_ESPECIAL = "horario_especial"
    TIPOS = [
        (FERIADO, "Feriado (no se cuenta tardanza)"),
        (HORARIO_ESPECIAL, "Horario especial (otra hora de entrada ese día)"),
    ]

    fecha = models.DateField(unique=True)
    tipo = models.CharField(max_length=20, choices=TIPOS)
    hora_entrada_especial = models.TimeField(
        null=True,
        blank=True,
        help_text="Solo para horario especial: hora de entrada esperada ese día.",
    )
    descripcion = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"{self.fecha} - {self.get_tipo_display()}"


class Institucion(models.Model):
    """
    Ubicación y radio que definen el perímetro donde se reconoce la asistencia.
    Es un registro único (singleton): siempre existe una sola institución.
    El administrador lo edita desde el panel, con un mapa.
    """

    nombre = models.CharField(max_length=120, default="Institución")
    latitud = models.FloatField()
    longitud = models.FloatField()
    radio_metros = models.PositiveIntegerField(
        default=100,
        help_text="Distancia máxima (en metros) desde el punto para poder marcar.",
    )

    class Meta:
        verbose_name = "Ubicación de la institución"
        verbose_name_plural = "Ubicación de la institución"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.pk = 1  # fuerza que siempre sea el mismo registro
        super().save(*args, **kwargs)

    @classmethod
    def obtener(cls):
        """Devuelve el registro único, creándolo con valores por defecto si no existe."""
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={"latitud": -16.5, "longitud": -68.15, "radio_metros": 100},
        )
        return obj


from django.utils import timezone as _tz
from datetime import timedelta as _td


class LoginSecurity(models.Model):
    UMBRAL = 3  # fallos antes de empezar a bloquear
    # Duración del bloqueo según el nivel (en segundos): 30s, 1m, 2m, 5m, 10m
    DURACIONES = {1: 30, 2: 60, 3: 120, 4: 300, 5: 600}
    TOPE = 900  # 15 min a partir del nivel 6

    usuario = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="login_security"
    )
    intentos_fallidos = models.PositiveIntegerField(default=0)
    nivel_bloqueo = models.PositiveIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    ultimo_intento = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.usuario.username

    def esta_bloqueado(self):
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > _tz.now())

    def segundos_restantes(self):
        if not self.bloqueado_hasta:
            return 0
        return max(0, int((self.bloqueado_hasta - _tz.now()).total_seconds()))

    def _duracion(self, nivel):
        return self.DURACIONES.get(nivel, self.TOPE)

    def registrar_fallo(self):
        now = _tz.now()
        self.ultimo_intento = now
        if self.esta_bloqueado():
            self.save()
            return
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= self.UMBRAL:
            self.nivel_bloqueo += 1
            self.bloqueado_hasta = now + _td(seconds=self._duracion(self.nivel_bloqueo))
            self.intentos_fallidos = 0
        self.save()

    def registrar_exito(self):
        self.intentos_fallidos = 0
        self.nivel_bloqueo = 0
        self.bloqueado_hasta = None
        self.ultimo_intento = _tz.now()
        self.save()


from django.contrib.auth.signals import (
    user_login_failed as _fail_sig,
    user_logged_in as _ok_sig,
)
from django.dispatch import receiver as _receiver


@_receiver(_fail_sig)
def _registrar_login_fallido(sender, credentials, **kwargs):
    username = (credentials or {}).get("username")
    if not username:
        return
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return
    sec, _ = LoginSecurity.objects.get_or_create(usuario=user)
    sec.registrar_fallo()


@_receiver(_ok_sig)
def _registrar_login_exitoso(sender, request, user, **kwargs):
    sec, _ = LoginSecurity.objects.get_or_create(usuario=user)
    sec.registrar_exito()

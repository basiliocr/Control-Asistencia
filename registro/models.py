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

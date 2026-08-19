from datetime import datetime, timedelta
from math import radians, sin, cos, asin, sqrt

from django.conf import settings
from django.utils import timezone

from .models import Asistencia, DiaEspecial, Institucion


class ResultadoMarca:
    def __init__(self, ok, mensaje, asistencia=None):
        self.ok = ok
        self.mensaje = mensaje
        self.asistencia = asistencia


def distancia_metros(lat1, lng1, lat2, lng2):
    """Distancia en metros entre dos coordenadas (fórmula de Haversine)."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    )
    return 2 * R * asin(sqrt(a))


def registrar_con_gps(pasante, tipo, lat, lng):
    """Valida que el pasante esté dentro del radio configurado antes de registrar."""
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return ResultadoMarca(
            False, "No se recibió tu ubicación. Activa el GPS y vuelve a intentar."
        )

    inst = Institucion.obtener()
    distancia = distancia_metros(lat, lng, inst.latitud, inst.longitud)

    if distancia > inst.radio_metros:
        return ResultadoMarca(
            False,
            f"Estás a {distancia:.0f} m de la institución "
            f"(máximo permitido: {inst.radio_metros} m). Acércate para poder marcar.",
        )

    return registrar_marca(pasante, tipo)


def registrar_marca(pasante, tipo):
    ahora = timezone.localtime()
    hoy = ahora.date()
    hora_actual = ahora.time()

    if tipo == "ENTRADA":
        return _registrar_entrada(pasante, hoy, hora_actual)
    elif tipo == "SALIDA":
        return _registrar_salida(pasante, hoy, hora_actual)
    else:
        return ResultadoMarca(False, "Tipo de marca inválido.")


def _calcular_tardanza(pasante, fecha, hora_llegada):
    dia = DiaEspecial.objects.filter(fecha=fecha).first()

    if dia and dia.tipo == DiaEspecial.FERIADO:
        return 0

    if dia and dia.tipo == DiaEspecial.HORARIO_ESPECIAL and dia.hora_entrada_especial:
        hora_esperada = dia.hora_entrada_especial
    else:
        hora_esperada = pasante.horario_entrada

    tolerancia = getattr(settings, "TOLERANCIA_MINUTOS", 0)
    esperada_dt = datetime.combine(fecha, hora_esperada)
    limite_dt = esperada_dt + timedelta(minutes=tolerancia)
    llegada_dt = datetime.combine(fecha, hora_llegada)

    if llegada_dt <= limite_dt:
        return 0
    return int((llegada_dt - esperada_dt).total_seconds() // 60)


def _registrar_entrada(pasante, hoy, hora_actual):
    asistencia = Asistencia.objects.filter(pasante=pasante, fecha=hoy).first()

    if asistencia and asistencia.hora_entrada:
        return ResultadoMarca(
            False,
            f"{pasante.nombre} ya marcó entrada hoy a las "
            f"{asistencia.hora_entrada.strftime('%H:%M')}.",
            asistencia,
        )

    tardanza = _calcular_tardanza(pasante, hoy, hora_actual)

    if asistencia is None:
        asistencia = Asistencia(pasante=pasante, fecha=hoy)

    asistencia.hora_entrada = hora_actual
    asistencia.tardanza_min = tardanza
    asistencia.estado = Asistencia.ESTADO_SIN_SALIDA
    asistencia.save()

    hora_txt = hora_actual.strftime("%H:%M")
    if tardanza > 0:
        mensaje = f"Entrada registrada para {pasante.nombre} a las {hora_txt}. Tardanza: {tardanza} min."
    else:
        mensaje = (
            f"Entrada registrada para {pasante.nombre} a las {hora_txt}. A tiempo."
        )
    return ResultadoMarca(True, mensaje, asistencia)


def _registrar_salida(pasante, hoy, hora_actual):
    asistencia = Asistencia.objects.filter(pasante=pasante, fecha=hoy).first()

    if asistencia is None or not asistencia.hora_entrada:
        return ResultadoMarca(
            False,
            f"{pasante.nombre} no tiene una entrada registrada hoy. No se puede marcar salida.",
        )

    if asistencia.hora_salida:
        return ResultadoMarca(
            False,
            f"{pasante.nombre} ya marcó salida hoy a las "
            f"{asistencia.hora_salida.strftime('%H:%M')}.",
            asistencia,
        )

    asistencia.hora_salida = hora_actual
    asistencia.estado = Asistencia.ESTADO_COMPLETO
    asistencia.save()

    return ResultadoMarca(
        True,
        f"Salida registrada para {pasante.nombre} a las {hora_actual.strftime('%H:%M')}.",
        asistencia,
    )

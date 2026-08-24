"""
Lógica central de marcación de asistencia.
Valida ubicación (GPS) y dispositivo (celular vinculado) antes de registrar.
La hora la pone el servidor. Las coordenadas de cada marca se guardan.
"""

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
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    )
    return 2 * R * asin(sqrt(a))


def registrar_con_gps(pasante, tipo, lat, lng, dispositivo=None):
    # --- 1. Validar el dispositivo (celular vinculado) ---
    dispositivo = (dispositivo or "").strip()
    if not dispositivo:
        return ResultadoMarca(
            False,
            "No se pudo identificar tu dispositivo. Recarga la página e intenta de nuevo.",
        )

    if not pasante.dispositivo_id:
        pasante.dispositivo_id = dispositivo
        pasante.save(update_fields=["dispositivo_id"])
    elif pasante.dispositivo_id != dispositivo:
        return ResultadoMarca(
            False,
            "Este no es el dispositivo registrado para tu cuenta. Solo puedes marcar "
            "desde tu celular vinculado. Si cambiaste de teléfono, pide a un administrador "
            "que reinicie tu dispositivo.",
        )

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

    return registrar_marca(pasante, tipo, lat, lng)


def registrar_marca(pasante, tipo, lat=None, lng=None):
    ahora = timezone.localtime()
    hoy = ahora.date()
    hora_actual = ahora.time()

    if tipo == "ENTRADA":
        return _registrar_entrada(pasante, hoy, hora_actual, lat, lng)
    elif tipo == "SALIDA":
        return _registrar_salida(pasante, hoy, hora_actual, lat, lng)
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


def _registrar_entrada(pasante, hoy, hora_actual, lat=None, lng=None):
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
    asistencia.lat_entrada = lat
    asistencia.lng_entrada = lng
    asistencia.save()

    hora_txt = hora_actual.strftime("%H:%M")
    if tardanza > 0:
        mensaje = f"Entrada registrada para {pasante.nombre} a las {hora_txt}. Tardanza: {tardanza} min."
    else:
        mensaje = (
            f"Entrada registrada para {pasante.nombre} a las {hora_txt}. A tiempo."
        )
    return ResultadoMarca(True, mensaje, asistencia)


def _registrar_salida(pasante, hoy, hora_actual, lat=None, lng=None):
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
    asistencia.lat_salida = lat
    asistencia.lng_salida = lng
    asistencia.save()

    return ResultadoMarca(
        True,
        f"Salida registrada para {pasante.nombre} a las {hora_actual.strftime('%H:%M')}.",
        asistencia,
    )

"""
Genera datos de prueba para evaluar el sistema:
10 pasantes, cada uno con 100 asistencias en días hábiles.

Uso:
    python manage.py datos_prueba
    python manage.py datos_prueba --pasantes 10 --dias 100
    python manage.py datos_prueba --limpiar   (solo borra los datos de prueba)

Los datos de prueba se reconocen por el prefijo del usuario ("pasante_prueba_"),
así que el comando se puede volver a correr sin duplicar: primero limpia los
anteriores y vuelve a crear. NO toca a los pasantes reales.
"""

import random
from datetime import date, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.models import User

from registro.models import Pasante, Asistencia, Institucion
from registro.services import _calcular_tardanza

PREFIJO = "pasante_prueba_"

NOMBRES = [
    "Ana Quispe Mamani",
    "Luis Condori Flores",
    "María Chambi Apaza",
    "Carlos Mamani Huanca",
    "Rosa Villca Ticona",
    "Jorge Choque Laura",
    "Elena Colque Nina",
    "David Poma Cruz",
    "Sofía Yujra Alavi",
    "Miguel Calle Vargas",
    "Lucía Marca Quispe",
    "Pedro Huanca Mamani",
]
AREAS = ["Soporte", "Redes", "Infraestructura", "Mantenimiento", "Sistemas"]


class Command(BaseCommand):
    help = "Crea pasantes y asistencias de prueba para evaluar el sistema."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pasantes",
            type=int,
            default=10,
            help="Cuántos pasantes crear (por defecto 10).",
        )
        parser.add_argument(
            "--dias",
            type=int,
            default=100,
            help="Cuántas asistencias por pasante (por defecto 100).",
        )
        parser.add_argument(
            "--limpiar",
            action="store_true",
            help="Solo borra los datos de prueba y termina.",
        )

    def _limpiar(self):
        users = User.objects.filter(username__startswith=PREFIJO)
        n = users.count()
        for u in users:
            # Asistencia protege al pasante (PROTECT), así que se borran primero.
            pasante = getattr(u, "pasante", None)
            if pasante:
                Asistencia.objects.filter(pasante=pasante).delete()
                pasante.delete()
            u.delete()
        return n

    @transaction.atomic
    def handle(self, *args, **opciones):
        borrados = self._limpiar()
        if borrados:
            self.stdout.write(
                f"Se borraron {borrados} pasante(s) de prueba anteriores."
            )
        if opciones["limpiar"]:
            self.stdout.write(self.style.SUCCESS("Listo: datos de prueba eliminados."))
            return

        n_pas = opciones["pasantes"]
        n_dias = opciones["dias"]

        inst = Institucion.obtener()
        # Un punto aleatorio DENTRO del perímetro (radio en metros -> grados aprox.).
        radio_grados = (inst.radio_metros * 0.8) / 111320.0

        hoy = date.today()
        creados_pas = 0
        creadas_asis = 0

        for i in range(1, n_pas + 1):
            username = f"{PREFIJO}{i:02d}"
            user = User.objects.create_user(username=username, password="prueba1234")
            user.is_active = True
            user.save()

            pasante = Pasante.objects.create(
                user=user,
                nombre=NOMBRES[(i - 1) % len(NOMBRES)],
                ci=f"PRB{i:04d}",
                area=random.choice(AREAS),
                identificador=f"PRB-{i:02d}",
                horario_entrada=time(8, 30),
                horario_salida=time(16, 30),
                activo=True,
                dispositivo_id=f"disp-prueba-{i:02d}",
            )
            creados_pas += 1

            # 100 días hábiles hacia atrás desde hoy.
            fechas = []
            d = hoy
            while len(fechas) < n_dias:
                if d.weekday() < 5:  # 0-4 = lunes a viernes
                    fechas.append(d)
                d -= timedelta(days=1)

            nuevas = []
            for fecha in fechas:
                # Hora de entrada: la mayoría a tiempo, algunos con retraso.
                if random.random() < 0.75:
                    h, m = 8, random.randint(20, 35)  # 08:20-08:35 (a tiempo o leve)
                else:
                    h, m = 8, random.randint(36, 59)  # 08:36-08:59 (tardanza)
                hora_entrada = time(h, m)

                lat_e = inst.latitud + random.uniform(-radio_grados, radio_grados)
                lng_e = inst.longitud + random.uniform(-radio_grados, radio_grados)

                tardanza = _calcular_tardanza(pasante, fecha, hora_entrada)

                if random.random() < 0.08:
                    # 8%: entrada sin salida
                    hora_salida = None
                    lat_s = lng_s = None
                    estado = Asistencia.ESTADO_SIN_SALIDA
                else:
                    hora_salida = time(16, random.randint(25, 45))
                    lat_s = inst.latitud + random.uniform(-radio_grados, radio_grados)
                    lng_s = inst.longitud + random.uniform(-radio_grados, radio_grados)
                    estado = Asistencia.ESTADO_COMPLETO

                nuevas.append(
                    Asistencia(
                        pasante=pasante,
                        fecha=fecha,
                        hora_entrada=hora_entrada,
                        hora_salida=hora_salida,
                        tardanza_min=tardanza,
                        estado=estado,
                        lat_entrada=lat_e,
                        lng_entrada=lng_e,
                        lat_salida=lat_s,
                        lng_salida=lng_s,
                    )
                )

            Asistencia.objects.bulk_create(nuevas)
            creadas_asis += len(nuevas)
            self.stdout.write(
                f"  {pasante.identificador}  {pasante.nombre}: {len(nuevas)} asistencias"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo: {creados_pas} pasantes y {creadas_asis} asistencias de prueba. "
                f"Contraseña de todos: prueba1234"
            )
        )

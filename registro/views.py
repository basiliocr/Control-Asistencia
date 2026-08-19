import base64
from io import BytesIO

import qrcode
import openpyxl
from openpyxl.styles import Font, PatternFill

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Pasante, Asistencia, Institucion, DiaEspecial, Correccion
from .forms import PasanteForm, AsistenciaForm, DiaEspecialForm
from .services import registrar_con_gps


@login_required
def marcar(request):
    # Los administradores no marcan asistencia: van directo a su panel.
    if request.user.is_staff:
        return redirect("panel")
    if not hasattr(request.user, "pasante"):
        return render(request, "registro/marcar.html", {"sin_pasante": True})

    pasante = request.user.pasante
    resultado = None
    if request.method == "POST":
        resultado = registrar_con_gps(
            pasante,
            request.POST.get("tipo"),
            request.POST.get("lat"),
            request.POST.get("lng"),
        )

    inst = Institucion.obtener()
    return render(
        request,
        "registro/marcar.html",
        {
            "pasante": pasante,
            "resultado": resultado,
            "institucion_lat": inst.latitud,
            "institucion_lng": inst.longitud,
            "radio": inst.radio_metros,
        },
    )


@staff_member_required
def panel(request):
    hoy = timezone.localdate()
    return render(
        request,
        "registro/panel.html",
        {
            "institucion": Institucion.obtener(),
            "total_pasantes": Pasante.objects.filter(activo=True).count(),
            "asistencias_hoy": Asistencia.objects.filter(fecha=hoy).count(),
            "tardanzas_hoy": Asistencia.objects.filter(
                fecha=hoy, tardanza_min__gt=0
            ).count(),
        },
    )


@staff_member_required
def ubicacion(request):
    inst = Institucion.obtener()
    if request.method == "POST":
        try:
            nombre = (request.POST.get("nombre") or "").strip()
            inst.nombre = nombre or inst.nombre
            inst.latitud = float(request.POST.get("latitud"))
            inst.longitud = float(request.POST.get("longitud"))
            inst.radio_metros = int(request.POST.get("radio_metros"))
            inst.save()
            messages.success(request, "Ubicación y perímetro actualizados.")
            return redirect("ubicacion")
        except (TypeError, ValueError):
            messages.error(request, "Los valores ingresados no son válidos.")
    return render(request, "registro/ubicacion.html", {"inst": inst})


# --------------------------- Pasantes ---------------------------


@staff_member_required
def pasantes_lista(request):
    pasantes = Pasante.objects.select_related("user").order_by("nombre")
    return render(request, "registro/pasantes_lista.html", {"pasantes": pasantes})


@staff_member_required
def pasante_form(request, pk=None):
    pasante = get_object_or_404(Pasante, pk=pk) if pk else None
    if request.method == "POST":
        form = PasanteForm(request.POST, instance=pasante)
        if form.is_valid():
            username = form.cleaned_data["username"]
            password = form.cleaned_data["password"]
            if pasante is None:
                if not password:
                    form.add_error(
                        "password", "La contraseña es obligatoria al crear un pasante."
                    )
                else:
                    user = User.objects.create_user(
                        username=username, password=password
                    )
                    obj = form.save(commit=False)
                    obj.user = user
                    obj.save()
                    messages.success(request, f"Pasante «{obj.nombre}» creado.")
                    return redirect("pasantes_lista")
            else:
                user = pasante.user
                user.username = username
                if password:
                    user.set_password(password)
                user.save()
                form.save()
                messages.success(request, f"Pasante «{pasante.nombre}» actualizado.")
                return redirect("pasantes_lista")
    else:
        form = PasanteForm(instance=pasante)
    return render(
        request, "registro/pasante_form.html", {"form": form, "pasante": pasante}
    )


@staff_member_required
def pasante_eliminar(request, pk):
    pasante = get_object_or_404(Pasante, pk=pk)
    tiene_historial = pasante.asistencias.exists()
    if request.method == "POST":
        nombre = pasante.nombre
        if tiene_historial:
            pasante.activo = False
            pasante.save()
            messages.info(
                request,
                f"«{nombre}» tiene historial, así que fue dado de baja (no eliminado).",
            )
        else:
            user = pasante.user
            pasante.delete()
            user.delete()
            messages.success(request, f"Pasante «{nombre}» eliminado por completo.")
        return redirect("pasantes_lista")
    return render(
        request,
        "registro/pasante_eliminar.html",
        {"pasante": pasante, "tiene_historial": tiene_historial},
    )


# --------------------------- Planilla de asistencias ---------------------------


@staff_member_required
def asistencias_lista(request):
    asistencias, desde, hasta, pasante_id = _asistencias_filtradas(request)
    return render(
        request,
        "registro/asistencias_lista.html",
        {
            "asistencias": asistencias,
            "pasantes": Pasante.objects.order_by("nombre"),
            "desde": desde,
            "hasta": hasta,
            "pasante_id": pasante_id,
        },
    )


@staff_member_required
def asistencia_editar(request, pk):
    asistencia = get_object_or_404(Asistencia, pk=pk)
    if request.method == "POST":
        form = AsistenciaForm(request.POST, instance=asistencia)
        if form.is_valid():
            form.save()
            if form.changed_data:
                Correccion.objects.create(
                    asistencia=asistencia,
                    admin=request.user,
                    detalle=f"Editado desde el panel. Campos: {', '.join(form.changed_data)}.",
                )
            messages.success(
                request, "Asistencia actualizada. Se registró la corrección."
            )
            return redirect("asistencias_lista")
    else:
        form = AsistenciaForm(instance=asistencia)
    return render(
        request,
        "registro/asistencia_form.html",
        {"form": form, "asistencia": asistencia},
    )


@staff_member_required
def asistencia_eliminar(request, pk):
    asistencia = get_object_or_404(Asistencia, pk=pk)
    if request.method == "POST":
        asistencia.delete()
        messages.success(request, "Registro de asistencia eliminado.")
        return redirect("asistencias_lista")
    return render(
        request, "registro/asistencia_eliminar.html", {"asistencia": asistencia}
    )


# --------------------------- Días especiales ---------------------------


@staff_member_required
def dias_lista(request):
    dias = DiaEspecial.objects.order_by("-fecha")
    return render(request, "registro/dias_lista.html", {"dias": dias})


@staff_member_required
def dia_form(request, pk=None):
    dia = get_object_or_404(DiaEspecial, pk=pk) if pk else None
    if request.method == "POST":
        form = DiaEspecialForm(request.POST, instance=dia)
        if form.is_valid():
            form.save()
            messages.success(request, "Día especial guardado.")
            return redirect("dias_lista")
    else:
        form = DiaEspecialForm(instance=dia)
    return render(request, "registro/dia_form.html", {"form": form, "dia": dia})


@staff_member_required
def dia_eliminar(request, pk):
    dia = get_object_or_404(DiaEspecial, pk=pk)
    if request.method == "POST":
        dia.delete()
        messages.success(request, "Día especial eliminado.")
        return redirect("dias_lista")
    return render(request, "registro/dia_eliminar.html", {"dia": dia})


# --------------------------- Reportes ---------------------------


def _asistencias_filtradas(request):
    hoy = timezone.localdate()
    desde = request.GET.get("desde") or hoy.replace(day=1).isoformat()
    hasta = request.GET.get("hasta") or hoy.isoformat()
    pasante_id = request.GET.get("pasante") or ""
    asistencias = (
        Asistencia.objects.select_related("pasante")
        .filter(fecha__gte=desde, fecha__lte=hasta)
        .order_by("-fecha", "pasante__nombre")
    )
    if pasante_id:
        asistencias = asistencias.filter(pasante_id=pasante_id)
    return asistencias, desde, hasta, pasante_id


@staff_member_required
def reportes(request):
    asistencias, desde, hasta, pasante_id = _asistencias_filtradas(request)

    if request.GET.get("export") == "excel":
        return _exportar_excel(asistencias, desde, hasta)

    total = asistencias.count()
    con_tardanza = asistencias.filter(tardanza_min__gt=0).count()
    minutos_tardanza = sum(a.tardanza_min for a in asistencias)

    return render(
        request,
        "registro/reportes.html",
        {
            "asistencias": asistencias,
            "pasantes": Pasante.objects.order_by("nombre"),
            "desde": desde,
            "hasta": hasta,
            "pasante_id": pasante_id,
            "total": total,
            "con_tardanza": con_tardanza,
            "minutos_tardanza": minutos_tardanza,
        },
    )


def _exportar_excel(asistencias, desde, hasta):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Asistencias"
    ws.append(
        [
            "Pasante",
            "Identificador",
            "Área",
            "Fecha",
            "Entrada",
            "Salida",
            "Tardanza (min)",
            "Estado",
        ]
    )
    fuente = Font(bold=True, color="FFFFFF")
    relleno = PatternFill("solid", fgColor="17803D")
    for celda in ws[1]:
        celda.font = fuente
        celda.fill = relleno
    for a in asistencias:
        ws.append(
            [
                a.pasante.nombre,
                a.pasante.identificador,
                a.pasante.area,
                a.fecha.strftime("%d/%m/%Y"),
                a.hora_entrada.strftime("%H:%M") if a.hora_entrada else "",
                a.hora_salida.strftime("%H:%M") if a.hora_salida else "",
                a.tardanza_min,
                a.get_estado_display(),
            ]
        )
    for i, ancho in enumerate([22, 14, 16, 12, 10, 10, 14, 20], start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = ancho
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="asistencias_{desde}_a_{hasta}.xlsx"'
    )
    wb.save(response)
    return response


@staff_member_required
def planilla_pdf(request):
    """Genera la planilla oficial (PDF) de UN pasante en un rango de fechas."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
    )

    pasante_id = request.GET.get("pasante")
    if not pasante_id:
        messages.error(request, "Elige un pasante para generar su planilla.")
        return redirect("reportes")

    pasante = get_object_or_404(Pasante, pk=pasante_id)
    hoy = timezone.localdate()
    desde = request.GET.get("desde") or hoy.replace(day=1).isoformat()
    hasta = request.GET.get("hasta") or hoy.isoformat()

    asistencias = Asistencia.objects.filter(
        pasante=pasante, fecha__gte=desde, fecha__lte=hasta
    ).order_by("fecha")
    inst = Institucion.obtener()

    DIAS = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    centro = ParagraphStyle(
        "centro",
        fontName="Helvetica-Bold",
        fontSize=13,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    subt = ParagraphStyle(
        "subt",
        fontName="Helvetica-Bold",
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=10,
    )
    info = ParagraphStyle("info", fontName="Helvetica", fontSize=10, spaceAfter=4)

    elems = []
    elems.append(Paragraph(inst.nombre.upper(), centro))
    elems.append(
        Paragraph("PLANILLA DE ASISTENCIA - TRABAJO DIRIGIDO O PASANTÍA", subt)
    )
    elems.append(Paragraph(f"<b>Dependencia / Área:</b> {pasante.area}", info))
    elems.append(Paragraph(f"<b>Nombre del pasante:</b> {pasante.nombre}", info))
    elems.append(Paragraph(f"<b>C.I.:</b> {pasante.ci}", info))
    d = timezone.datetime.fromisoformat(desde).strftime("%d/%m/%Y")
    h = timezone.datetime.fromisoformat(hasta).strftime("%d/%m/%Y")
    elems.append(Paragraph(f"<b>Periodo:</b> del {d} al {h}", info))
    elems.append(Spacer(1, 8))

    data = [
        [
            "N\u00ba",
            "DÍA",
            "FECHA",
            "HORA DE\nINGRESO",
            "HORA DE\nSALIDA",
            "OBSERVACIONES",
        ]
    ]
    for i, a in enumerate(asistencias, start=1):
        obs = f"Tardanza: {a.tardanza_min} min" if a.tardanza_min else ""
        data.append(
            [
                str(i),
                DIAS[a.fecha.weekday()],
                a.fecha.strftime("%d/%m/%y"),
                a.hora_entrada.strftime("%H:%M") if a.hora_entrada else "",
                a.hora_salida.strftime("%H:%M") if a.hora_salida else "",
                obs,
            ]
        )
    for _ in range(max(0, 12 - len(asistencias))):
        data.append(["", "", "", "", "", ""])

    tabla = Table(
        data, colWidths=[12 * mm, 28 * mm, 24 * mm, 30 * mm, 30 * mm, 48 * mm]
    )
    tabla.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17803d")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (5, 0), (5, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f2f7f5")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elems.append(tabla)

    doc.build(elems)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="planilla_{pasante.identificador}.pdf"'
    )
    return response


def _qr_base64(texto):
    img = qrcode.make(texto)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


@staff_member_required
def credenciales(request):
    pasantes = Pasante.objects.filter(activo=True).order_by("nombre")
    tarjetas = [{"pasante": p, "qr": _qr_base64(p.identificador)} for p in pasantes]
    return render(request, "registro/credenciales.html", {"tarjetas": tarjetas})

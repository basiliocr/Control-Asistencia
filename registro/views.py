from io import BytesIO

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
from .forms import PasanteForm, AsistenciaForm, DiaEspecialForm, AdminUserForm
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
        tipo = request.POST.get("tipo")
        lat = request.POST.get("lat")
        lng = request.POST.get("lng")
        dispositivo = request.POST.get("dispositivo")
        resultado = registrar_con_gps(pasante, tipo, lat, lng, dispositivo)

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


def _coord(lat, lng):
    if lat is None or lng is None:
        return ""
    return f"{lat:.5f}, {lng:.5f}"


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
            "Ubicación ingreso",
            "Ubicación salida",
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
                _coord(a.lat_entrada, a.lng_entrada),
                _coord(a.lat_salida, a.lng_salida),
            ]
        )
    for i, ancho in enumerate([22, 14, 16, 12, 9, 9, 12, 18, 22, 22], start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = ancho
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="asistencias_{desde}_a_{hasta}.xlsx"'
    )
    wb.save(response)
    return response


def admins_lista(request):
    admins = User.objects.filter(is_staff=True).order_by("username")
    return render(request, "registro/admins_lista.html", {"admins": admins})


@staff_member_required
def admin_form(request, pk=None):
    admin_user = get_object_or_404(User, pk=pk, is_staff=True) if pk else None

    if request.method == "POST":
        form = AdminUserForm(request.POST, instance=admin_user)
        if form.is_valid():
            password = form.cleaned_data["password"]

            if admin_user is None:
                if not password:
                    form.add_error(
                        "password",
                        "La contraseña es obligatoria al crear un administrador.",
                    )
                else:
                    obj = form.save(commit=False)
                    obj.is_staff = True
                    obj.set_password(password)
                    obj.save()
                    messages.success(request, f"Administrador «{obj.username}» creado.")
                    return redirect("admins_lista")
            else:
                # Protección: nadie se desactiva ni se quita superusuario a sí mismo.
                if admin_user.pk == request.user.pk:
                    form.instance.is_active = True
                    if (
                        not form.cleaned_data.get("is_superuser")
                        and admin_user.is_superuser
                    ):
                        messages.error(
                            request,
                            "No puedes quitarte tus propios permisos de superusuario.",
                        )
                        return render(
                            request,
                            "registro/admin_form.html",
                            {"form": form, "admin_user": admin_user},
                        )

                obj = form.save(commit=False)
                obj.is_staff = True
                if password:
                    obj.set_password(password)
                obj.save()
                messages.success(
                    request, f"Administrador «{obj.username}» actualizado."
                )
                return redirect("admins_lista")
    else:
        form = AdminUserForm(instance=admin_user)

    return render(
        request, "registro/admin_form.html", {"form": form, "admin_user": admin_user}
    )


@staff_member_required
def admin_eliminar(request, pk):
    admin_user = get_object_or_404(User, pk=pk, is_staff=True)

    if admin_user.pk == request.user.pk:
        messages.error(request, "No puedes eliminar tu propia cuenta.")
        return redirect("admins_lista")

    if request.method == "POST":
        nombre = admin_user.username
        admin_user.delete()
        messages.success(request, f"Administrador «{nombre}» eliminado.")
        return redirect("admins_lista")

    return render(request, "registro/admin_eliminar.html", {"admin_user": admin_user})


@staff_member_required
def pasante_reset_dispositivo(request, pk):
    pasante = get_object_or_404(Pasante, pk=pk)
    pasante.dispositivo_id = ""
    pasante.save(update_fields=["dispositivo_id"])
    messages.success(
        request,
        f"Dispositivo de «{pasante.nombre}» reiniciado. Podrá vincular un celular nuevo en su próxima marca.",
    )
    return redirect("pasantes_lista")


@staff_member_required
def planilla_word(request):
    """Planilla oficial en PDF (formato El Alto): encabezado/pie con imagen,
    sin columnas de FIRMA, recuadro de sello 2.7 x 3 cm, coordenadas en observaciones.
    (El nombre de la función queda igual para no cambiar urls.py.)"""
    import os
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import mm, cm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
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
    DIAS = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]

    base_img = os.path.join(os.path.dirname(__file__), "static", "img")
    img_h = os.path.join(base_img, "encabezado_el_alto.png")
    img_f = os.path.join(base_img, "pie_pagina.png")

    def marco(canvas, doc):
        W, H = LETTER
        hw = W - 24 * mm
        hh = hw * 0.1845
        if os.path.exists(img_h):
            canvas.drawImage(
                img_h, 12 * mm, H - 8 * mm - hh, width=hw, height=hh, mask="auto"
            )
        fw = W - 24 * mm
        fh = fw * 0.2267
        if os.path.exists(img_f):
            canvas.drawImage(img_f, 12 * mm, 2 * mm, width=fw, height=fh, mask="auto")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        topMargin=48 * mm,
        bottomMargin=46 * mm,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
    )

    titulo = ParagraphStyle(
        "t", fontName="Helvetica-Bold", fontSize=12, alignment=TA_CENTER, spaceAfter=10
    )
    info = ParagraphStyle(
        "i", fontName="Helvetica", fontSize=9, spaceAfter=3, leading=12
    )
    info_b = ParagraphStyle("ib", fontName="Helvetica-Bold", fontSize=8, spaceAfter=3)
    sello = ParagraphStyle(
        "s",
        fontName="Helvetica",
        fontSize=6.5,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#777777"),
    )
    hcab = ParagraphStyle(
        "h", fontName="Helvetica-Bold", fontSize=8, alignment=TA_CENTER, leading=10
    )
    obs_st = ParagraphStyle(
        "o", fontName="Helvetica", fontSize=7, alignment=TA_LEFT, leading=8.5
    )

    d = timezone.datetime.fromisoformat(desde).strftime("%d/%m/%Y")
    h = timezone.datetime.fromisoformat(hasta).strftime("%d/%m/%Y")

    elems = []
    elems.append(
        Paragraph("<u>PLANILLA DE ASISTENCIA TRABAJO DIRIGIDO O PASANTÍA</u>", titulo)
    )

    # Recuadro del sello: 2.7 cm de ancho x 3 cm de alto, con borde.
    sello_inner = Table(
        [[Paragraph("SELLO DE LA<br/>DEPENDENCIA", sello)]],
        colWidths=[2.7 * cm],
        rowHeights=[3 * cm],
    )
    sello_inner.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (0, 0), 0.8, colors.HexColor("#888888")),
                ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ]
        )
    )

    info_cell = [
        Paragraph(f"<b>DEPENDENCIA:</b> {pasante.area}", info),
        Spacer(1, 10),
        Paragraph("<b>FIRMA Y SELLO DEL SUPERVISOR</b>", info_b),
        Spacer(1, 6),
        Paragraph(
            f"<b>NOMBRE DEL PASANTE:</b> {pasante.nombre} &nbsp;&nbsp; <b>C.I.:</b> {pasante.ci}",
            info,
        ),
        Paragraph(f"<b>FECHA DESDE EL MES DE:</b> {d} &nbsp; <b>AL:</b> {h}", info),
    ]
    htbl = Table([[info_cell, sello_inner]], colWidths=[132 * mm, 54 * mm])
    htbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ]
        )
    )
    elems.append(htbl)
    elems.append(Spacer(1, 10))

    # Tabla SIN columnas de FIRMA (7 columnas)
    cab = [
        Paragraph(t, hcab)
        for t in [
            "Nº",
            "DIA",
            "FECHA",
            "HORA DE<br/>INGRESO",
            "HORA DE<br/>SALIDA",
            "OBSERVACIONES",
            "VºBº<br/>SUPERVISOR",
        ]
    ]
    data = [cab]

    for i, a in enumerate(asistencias, start=1):
        obs = []
        if a.lat_entrada is not None:
            obs.append(f"Ing: {a.lat_entrada:.5f}, {a.lng_entrada:.5f}")
        if a.lat_salida is not None:
            obs.append(f"Sal: {a.lat_salida:.5f}, {a.lng_salida:.5f}")
        if a.tardanza_min:
            obs.append(f"Tard: {a.tardanza_min} min")
        data.append(
            [
                str(i),
                DIAS[a.fecha.weekday()],
                a.fecha.strftime("%d/%m/%y"),
                a.hora_entrada.strftime("%H:%M") if a.hora_entrada else "",
                a.hora_salida.strftime("%H:%M") if a.hora_salida else "",
                Paragraph("<br/>".join(obs), obs_st),
                "",
            ]
        )
    for _ in range(max(0, 14 - len(asistencias))):
        data.append([""] * 7)

    tbl = Table(
        data,
        colWidths=[9 * mm, 24 * mm, 20 * mm, 24 * mm, 24 * mm, 58 * mm, 27 * mm],
        repeatRows=1,
    )
    tbl.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, -1), 8.5),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elems.append(tbl)

    doc.build(elems, onFirstPage=marco, onLaterPages=marco)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'inline; filename="planilla_{pasante.identificador}.pdf"'
    )
    return response

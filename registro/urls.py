from django.urls import path
from . import views

urlpatterns = [
    path("", views.marcar, name="marcar"),
    path("panel/", views.panel, name="panel"),
    path("gestion/ubicacion/", views.ubicacion, name="ubicacion"),
    path("gestion/pasantes/", views.pasantes_lista, name="pasantes_lista"),
    path("gestion/pasantes/nuevo/", views.pasante_form, name="pasante_nuevo"),
    path(
        "gestion/pasantes/<int:pk>/editar/", views.pasante_form, name="pasante_editar"
    ),
    path(
        "gestion/pasantes/<int:pk>/eliminar/",
        views.pasante_eliminar,
        name="pasante_eliminar",
    ),
    path("gestion/asistencias/", views.asistencias_lista, name="asistencias_lista"),
    path(
        "gestion/asistencias/<int:pk>/editar/",
        views.asistencia_editar,
        name="asistencia_editar",
    ),
    path(
        "gestion/asistencias/<int:pk>/eliminar/",
        views.asistencia_eliminar,
        name="asistencia_eliminar",
    ),
    path("gestion/dias/", views.dias_lista, name="dias_lista"),
    path("gestion/dias/nuevo/", views.dia_form, name="dia_nuevo"),
    path(
        "gestion/dias/cargar-feriados/",
        views.dias_cargar_feriados,
        name="dias_cargar_feriados",
    ),
    path(
        "gestion/dias/recalcular/",
        views.dias_recalcular_tardanzas,
        name="dias_recalcular_tardanzas",
    ),
    path("gestion/dias/<int:pk>/editar/", views.dia_form, name="dia_editar"),
    path("gestion/dias/<int:pk>/eliminar/", views.dia_eliminar, name="dia_eliminar"),
    path("gestion/admins/", views.admins_lista, name="admins_lista"),
    path("gestion/admins/nuevo/", views.admin_form, name="admin_nuevo"),
    path("gestion/admins/<int:pk>/editar/", views.admin_form, name="admin_editar"),
    path(
        "gestion/admins/<int:pk>/eliminar/", views.admin_eliminar, name="admin_eliminar"
    ),
    path("reportes/", views.reportes, name="reportes"),
    path("reportes/planilla/", views.planilla_word, name="planilla_pdf"),
    path(
        "gestion/pasantes/<int:pk>/reset-dispositivo/",
        views.pasante_reset_dispositivo,
        name="pasante_reset_dispositivo",
    ),
]

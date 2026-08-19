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
    path("gestion/dias/", views.dias_lista, name="dias_lista"),
    path("gestion/dias/nuevo/", views.dia_form, name="dia_nuevo"),
    path("gestion/dias/<int:pk>/editar/", views.dia_form, name="dia_editar"),
    path("gestion/dias/<int:pk>/eliminar/", views.dia_eliminar, name="dia_eliminar"),
    path(
        "gestion/asistencias/<int:pk>/eliminar/",
        views.asistencia_eliminar,
        name="asistencia_eliminar",
    ),
    path("reportes/", views.reportes, name="reportes"),
    path("credenciales/", views.credenciales, name="credenciales"),
    path("reportes/planilla/", views.planilla_pdf, name="planilla_pdf"),
]

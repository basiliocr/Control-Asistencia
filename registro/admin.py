from django import forms
from django.contrib import admin

from .models import Pasante, Asistencia, Correccion, DiaEspecial, Institucion

admin.site.site_header = "Sub Alcaldía — Control de Asistencia"
admin.site.site_title = "Asistencia"
admin.site.index_title = "Administración del sistema"


@admin.register(Pasante)
class PasanteAdmin(admin.ModelAdmin):
    list_display = (
        "identificador",
        "nombre",
        "area",
        "horario_entrada",
        "horario_salida",
        "activo",
    )
    list_editable = ("activo",)  # activar/desactivar desde la lista
    list_filter = ("area", "activo")
    search_fields = ("nombre", "ci", "identificador")
    ordering = ("nombre",)
    actions = ("dar_de_baja", "reactivar")

    @admin.action(description="Dar de baja (desactivar) los seleccionados")
    def dar_de_baja(self, request, queryset):
        n = queryset.update(activo=False)
        self.message_user(request, f"{n} pasante(s) dados de baja.")

    @admin.action(description="Reactivar los seleccionados")
    def reactivar(self, request, queryset):
        n = queryset.update(activo=True)
        self.message_user(request, f"{n} pasante(s) reactivados.")


@admin.register(Asistencia)
class AsistenciaAdmin(admin.ModelAdmin):
    list_display = (
        "pasante",
        "fecha",
        "hora_entrada",
        "hora_salida",
        "tardanza_min",
        "estado",
    )
    # Edición rápida de la planilla directamente desde la lista:
    list_editable = ("hora_entrada", "hora_salida", "tardanza_min", "estado")
    list_filter = ("estado", "fecha", "pasante__area")
    search_fields = ("pasante__nombre", "pasante__identificador")
    autocomplete_fields = ("pasante",)  # buscador al crear una a mano
    date_hierarchy = "fecha"
    ordering = ("-fecha",)

    def save_model(self, request, obj, form, change):
        """Al editar una asistencia existente, deja constancia de quién y qué cambió."""
        super().save_model(request, obj, form, change)
        if change and form.changed_data:
            campos = ", ".join(form.changed_data)
            Correccion.objects.create(
                asistencia=obj,
                admin=request.user,
                detalle=f"Editado desde el panel. Campos modificados: {campos}.",
            )


@admin.register(Correccion)
class CorreccionAdmin(admin.ModelAdmin):
    """Registro de auditoría: solo lectura, se genera solo."""

    list_display = ("asistencia", "admin", "fecha_hora", "detalle")
    search_fields = ("asistencia__pasante__nombre",)
    date_hierarchy = "fecha_hora"
    readonly_fields = ("asistencia", "admin", "fecha_hora", "detalle")

    def has_add_permission(self, request):
        return False


@admin.register(DiaEspecial)
class DiaEspecialAdmin(admin.ModelAdmin):
    list_display = ("fecha", "tipo", "hora_entrada_especial", "descripcion")
    list_filter = ("tipo",)
    date_hierarchy = "fecha"
    ordering = ("-fecha",)


class InstitucionForm(forms.ModelForm):
    latitud = forms.FloatField(localize=False)
    longitud = forms.FloatField(localize=False)

    class Meta:
        model = Institucion
        fields = "__all__"


@admin.register(Institucion)
class InstitucionAdmin(admin.ModelAdmin):
    form = InstitucionForm
    list_display = ("nombre", "latitud", "longitud", "radio_metros")
    change_form_template = "admin/registro/institucion_change.html"

    def has_add_permission(self, request):
        return not Institucion.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

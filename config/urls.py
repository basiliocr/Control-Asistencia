from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include

# El admin de Django, cuando no hay sesión iniciada, muestra su propio login gris.
# Con esta línea lo obligamos a usar NUESTRO login (el bonito) en su lugar.
admin.site.login = login_required(admin.site.login)

urlpatterns = [
    path("gestion-interna/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("registro.urls")),
]

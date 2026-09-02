from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect
from registro.forms import LoginConBloqueoForm

# El panel gris de Django (admin) es SOLO para staff.
# - Si entra alguien sin sesión -> lo mandamos a NUESTRO login (verde).
# - Si entra un pasante ya autenticado -> en vez de mostrarle el login gris de
#   "no autorizado", lo mandamos a su pantalla normal (la raíz).
_admin_login_original = admin.site.login


@login_required
def _admin_login(request, extra_context=None):
    if not request.user.is_staff:
        return redirect("/")
    return _admin_login_original(request, extra_context)


admin.site.login = _admin_login

urlpatterns = [
    path("gestion-interna/", admin.site.urls),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(authentication_form=LoginConBloqueoForm),
        name="login",
    ),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("registro.urls")),
]

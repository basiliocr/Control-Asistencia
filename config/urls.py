from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path, include
from django.contrib.auth import views as auth_views
from registro.forms import LoginConBloqueoForm

# El admin de Django, cuando no hay sesión iniciada, muestra su propio login gris.
# Con esta línea lo obligamos a usar NUESTRO login (el bonito) en su lugar.
admin.site.login = login_required(admin.site.login)

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

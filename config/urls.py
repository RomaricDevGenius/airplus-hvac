"""
URL configuration for web_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path
from web_project.views import SystemView

urlpatterns = [
    path("", include("apps.front.urls")),
    path("gestion/", include("apps.sample.urls")),
    path("admin/", admin.site.urls),
    path("", include("apps.pages.urls")),
    # Réinitialisation du mot de passe
    path(
        "compte/mot-de-passe-oublie/",
        auth_views.PasswordResetView.as_view(
            template_name="admin/gestion/password_reset_form.html",
            email_template_name="admin/gestion/password_reset_email.html",
            subject_template_name="admin/gestion/password_reset_subject.txt",
            success_url="/compte/mot-de-passe-oublie/envoye/",
        ),
        name="password_reset",
    ),
    path(
        "compte/mot-de-passe-oublie/envoye/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="admin/gestion/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "compte/reinitialisation/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="admin/gestion/password_reset_confirm.html",
            success_url="/compte/reinitialisation/termine/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "compte/reinitialisation/termine/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="admin/gestion/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = SystemView.as_view(template_name="pages_misc_error.html", status=404)
handler403 = SystemView.as_view(template_name="pages_misc_not_authorized.html", status=403)
handler400 = SystemView.as_view(template_name="pages_misc_error.html", status=400)
handler500 = SystemView.as_view(template_name="pages_misc_error.html", status=500)

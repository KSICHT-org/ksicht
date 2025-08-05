"""ksicht URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.2/topics/http/urls/
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
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django_registration.backends.activation import views as reg_views

from . import forms, views

sitemaps = {}

urlpatterns = (
    [
        path("", include("ksicht.core.urls", "core")),
        path("admin/", admin.site.urls),
        path("markdownx/", include("markdownx.urls")),
        re_path(r"^select2/", include("django_select2.urls")),
        path(
            "sitemap.xml",
            sitemap,
            {"sitemaps": sitemaps},
            name="django.contrib.sitemaps.views.sitemap",
        ),
        path(
            "ucty/prihlaseni/",
            auth_views.LoginView.as_view(
                template_name="registration/login.html",
                form_class=forms.KsichtAuthenticationForm,
            ),
            name="login",
        ),
        path(
            "ucty/profil/",
            views.UserProfileEditView.as_view(),
            name="edit_profile",
        ),
        path("ucty/odhlaseni/", auth_views.LogoutView.as_view(), name="logout"),
        path(
            "ucty/zmena-hesla/",
            auth_views.PasswordChangeView.as_view(
                form_class=forms.KsichtChangePasswordForm
            ),
            name="password_change",
        ),
        path(
            "ucty/zmena-hesla/hotovo/",
            auth_views.PasswordChangeDoneView.as_view(),
            name="password_change_done",
        ),
        path(
            "ucty/zapomenute-heslo/",
            auth_views.PasswordResetView.as_view(
                form_class=forms.KsichtPasswordResetForm
            ),
            name="password_reset",
        ),
        path(
            "ucty/zapomenute-heslo/hotovo/",
            auth_views.PasswordResetDoneView.as_view(),
            name="password_reset_done",
        ),
        path(
            "ucty/zapomenute-heslo/overeni/<uidb64>/<token>/",
            auth_views.PasswordResetConfirmView.as_view(
                form_class=forms.KsichtSetPasswordForm
            ),
            name="password_reset_confirm",
        ),
        path(
            "ucty/zapomenute-heslo/dokonceno/",
            auth_views.PasswordResetCompleteView.as_view(),
            name="password_reset_complete",
        ),
        path(
            "ucty/aktivace/dokonceno/",
            TemplateView.as_view(
                template_name="django_registration/activation_complete.html"
            ),
            name="django_registration_activation_complete",
        ),
        # The activation key can make use of any character from the
        # URL-safe base64 alphabet, plus the colon as a separator.
        re_path(
            r"^ucty/aktivace/",
            views.KsichtActivationView.as_view(),
            name="django_registration_activate",
        ),
        path(
            "ucty/registrace/",
            reg_views.RegistrationView.as_view(form_class=forms.KsichtRegistrationForm),
            name="django_registration_register",
        ),
        path(
            "ucty/registrace/dokonceno/",
            TemplateView.as_view(
                template_name="django_registration/registration_complete.html"
            ),
            name="django_registration_complete",
        ),
        path(
            "ucty/registrace-uzavrena/",
            TemplateView.as_view(
                template_name="django_registration/registration_closed.html"
            ),
            name="django_registration_disallowed",
        ),
    ]
    + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    + [
        path("<path:url>", views.permission_protected_flatpage),
    ]
)


if settings.DEBUG_TOOLBAR:
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns

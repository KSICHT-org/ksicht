from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.views import render_flatpage
from django.contrib.sites.shortcuts import get_current_site
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.generic import UpdateView
import pydash as py_
from django_registration.backends.activation.views import ActivationView

from . import forms


class UserProfileEditView(UpdateView):
    form_class = forms.KsichtEditProfileForm
    template_name = "registration/user_change_form.html"
    success_url = reverse_lazy("core:home")

    @method_decorator(csrf_protect)
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.request.user

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if hasattr(self, "object") and self.object.is_participant():
            kwargs.update(
                {
                    "initial": py_.pick(
                        self.object.participant_profile, self.form_class.PROFILE_FIELDS
                    )
                }
            )
        return kwargs

    def form_valid(self, form):
        messages.add_message(
            self.request,
            messages.SUCCESS,
            "<i class='fas fa-check-circle notification-icon'></i> Váš profil byl aktualizován</strong>.",
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["no_birth_date"] = self.object.participant_profile.birth_date is None
        return context


class KsichtActivationView(ActivationView):
    def form_invalid(self, form):
        super().form_invalid(form)

        extra_context = {"is_form_invalid": True, "form_error": form.errors.get("activation_key")}

        context_data = self.get_context_data()
        context_data.update(extra_context)
        return self.render_to_response(context_data)

def permission_protected_flatpage(request, url):
    """
    Exactly the same as normal FlatPage view which just verifies the access.
    """
    if not url.startswith("/"):
        url = "/" + url

    site_id = get_current_site(request).id

    try:
        f = get_object_or_404(FlatPage, url=url, sites=site_id)

        if hasattr(f, "metadata") and not f.metadata.is_accessible_for(request.user):
            if not request.user.is_authenticated:
                return HttpResponseRedirect(
                    reverse_lazy(settings.LOGIN_URL) + "?next=" + request.path
                )
            raise PermissionDenied
    except Http404:
        if not url.endswith("/") and settings.APPEND_SLASH:
            url += "/"
            f = get_object_or_404(FlatPage, url=url, sites=site_id)
            return HttpResponsePermanentRedirect(f"{request.path}/")

        raise

    return render_flatpage(request, f)

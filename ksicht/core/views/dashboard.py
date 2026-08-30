from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from .helpers import CurrentGradeMixin
from .. import models


__all__ = ("HomeView", "OrganizersView")


class HomeView(CurrentGradeMixin, TemplateView):
    template_name = "core/home.html"


@method_decorator([login_required, user_passes_test(lambda u: u.is_staff)], name="dispatch")
class OrganizersView(CurrentGradeMixin, TemplateView):
    template_name = "core/organizers.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_grades = models.Grade.objects.all().order_by("-end_date")
        context["all_grades"] = all_grades

        grade_id = self.request.GET.get("rocnik")
        selected_grade = None
        if grade_id:
            try:
                selected_grade = models.Grade.objects.filter(pk=grade_id).first()
            except Exception:
                pass
            if not selected_grade:
                selected_grade = models.Grade.objects.filter(school_year__icontains=grade_id).first()
        if not selected_grade:
            selected_grade = context.get("current_grade") or all_grades.first()

        context["selected_grade"] = selected_grade
        if selected_grade:
            context["all_series"] = selected_grade.series.all().prefetch_related("tasks")
        return context

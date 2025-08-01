import csv
from decimal import Decimal
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic.detail import BaseDetailView, DetailView
from django.views.generic.edit import BaseFormView
import pydash as py_

from .. import forms, models
from .decorators import current_grade_exists, is_participant


__all__ = (
    "CurrentGradeView",
    "CurrentGradeApplicationView",
    "GradeResultsExportView",
)

from ..models import Participant


@method_decorator(current_grade_exists, name="dispatch")
class CurrentGradeView(DetailView):
    template_name = "core/current_grade.html"

    def get_object(self, queryset=None):
        return models.Grade.objects.get_current()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["is_participant"] = (
            self.request.user.is_authenticated and self.request.user.is_participant()
        )
        data["is_grade_participant"] = (
            self.request.user.is_authenticated
            and self.object.participants.filter(user=self.request.user).exists()
        )
        data["can_apply"] = data["is_participant"] and not data["is_grade_participant"]
        data["has_birth_date"] = (
            hasattr(self.request.user, "participant_profile")
            and self.request.user.participant_profile.birth_date is not None
        )
        data["is_graduate"] = (
            hasattr(self.request.user, "participant_profile")
            and self.request.user.participant_profile.school_year is Participant.GRADE_CHOICES[0][0]
        )

        data["application_form"] = forms.CurrentGradeAppliationForm(has_birth_date=data["has_birth_date"], is_graduate=data["is_graduate"])
        return data


@method_decorator(
    [current_grade_exists, login_required, is_participant], name="dispatch"
)
class CurrentGradeApplicationView(BaseFormView):
    form_class = forms.CurrentGradeAppliationForm

    def get(self, request, *args, **kwargs):
        return redirect("core:current_grade")

    def form_valid(self, *args, **kwargs):
        user = self.request.user

        if not user.is_authenticated:
            return self.form_invalid()

        grade = models.Grade.objects.get_current()

        if not grade:
            return self.form_invalid()

        can_apply = (
            user.is_participant and not grade.participants.filter(user=user).exists()
        )

        if can_apply:
            grade.participants.add(
                user.participant_profile,
                through_defaults={
                    "participant_current_grade": user.participant_profile.school_year
                },
            )

        messages.add_message(
            self.request,
            messages.SUCCESS,
            "<i class='fas fa-check-circle notification-icon'></i> Přihlášení do KSICHTu proběhlo úspěšně. Hurá na řešení!</strong>.",
        )

        return redirect("core:current_grade")

    def form_invalid(self, *args, **kwargs):
        return redirect("core:current_grade")


class GradeResultsExportView(BaseDetailView):
    queryset = models.Grade.objects.all()

    def render_to_response(self, context):
        grade = context["object"]

        all_tasks = models.Task.objects.filter(series__grade=grade)
        all_submissions = models.TaskSolutionSubmission.objects.filter(
            task__in=all_tasks
        )
        all_applications = models.GradeApplication.objects.filter(
            grade=grade
        ).prefetch_related("participant__user")

        response = HttpResponse(content_type="text/csv")
        filename = quote(f"{grade} - výsledky.csv")
        response["Content-Disposition"] = f"attachment; filename*=utf-8''{filename}"

        task_headers = [f"Body {t.series} - {t}" for t in all_tasks]

        writer = csv.writer(response)
        writer.writerow(
            [
                "Pořadí",
                "Jméno",
                "Příjmení",
                "Ročník",
                "Škola",
            ]
            + task_headers
            + ["Body celkem"]
        )

        # This closely mirrors GradeSeries.get_rankings.
        # But it includes all tasks in all series.

        def _find_application(app_id):
            return py_.find(all_applications, lambda a: a.pk == app_id)

        def _find_task(task_id):
            return py_.find(all_tasks, lambda t: t.pk == task_id)

        scoring_dict = {
            a: {"by_tasks": {t: None for t in all_tasks}, "total": Decimal("0")}
            for a in all_applications
        }

        for s in all_submissions:
            a = _find_application(s.application_id)
            t = _find_task(s.task_id)

            if t:
                scoring_dict[a]["by_tasks"][t] = s.score

            scoring_dict[a]["total"] += s.score or Decimal("0")

        scoring = [
            (application, scores["by_tasks"], scores["total"])
            for (application, scores) in scoring_dict.items()
        ]

        # Attach ranks
        sorted_scoring = [
            # (application, rank, task scores, total score)
            (row[0], index + 1, row[1], row[2])
            for (index, row) in enumerate(
                sorted(scoring, key=lambda r: r[2], reverse=True)
            )
        ]

        for application, rank, task_scores, total_score in sorted_scoring:
            writer.writerow(
                [
                    f"{rank}.",
                    application.participant.user.first_name,
                    application.participant.user.last_name,
                    f"{application.participant_current_grade}.",
                    application.participant.school,
                ]
                + [task_scores[t] or "-" for t in all_tasks]
                + [total_score]
            )

        return response

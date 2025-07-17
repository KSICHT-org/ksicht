from collections import OrderedDict
from functools import reduce
from operator import or_
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import models, transaction
from django.forms import formset_factory, modelformset_factory
from django.http.response import HttpResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import FormView, TemplateView
from django.views.generic.edit import DeleteView

from ksicht import pdf
from .. import forms
from ..models import (
    Grade,
    GradeApplication,
    GradeSeries,
    Participant,
    Sticker,
    Task,
    TaskSolutionSubmission,
)
from .decorators import current_grade_exists, is_participant


__all__ = (
    "SolutionSubmitView",
    "SubmissionOverview",
    "ScoringView",
    "SolutionSubmitDeleteView",
    "SolutionExportView",
)


@method_decorator(
    [current_grade_exists, login_required, is_participant], name="dispatch"
)
class SolutionSubmitView(TemplateView):
    template_name = "core/solution_submit.html"

    def dispatch(self, request, *args, **kwargs):
        self.current_grade = Grade.objects.get_current()

        if not self.current_grade:
            return HttpResponseNotFound()

        self.current_series = self.current_grade.get_current_series()

        if not self.current_series:
            return HttpResponseNotFound()

        self.application = GradeApplication.objects.filter(
            participant=self.request.user.participant_profile,
            grade=self.current_grade,
        ).first()

        if not self.application:
            return HttpResponseNotFound()

        self.series_tasks = self.current_series.tasks.all()

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "current_grade": self.current_grade,
                "current_series": self.current_series,
                "forms": self.get_forms() if "forms" not in kwargs else kwargs["forms"],
            }
        )
        return context

    def get_forms(self):
        task_submissions = {
            submission.task_id: submission
            for submission in TaskSolutionSubmission.objects.filter(
                application=self.application, task__in=self.series_tasks
            )
        }
        form_task_id = self.request.GET.get("task_id")
        formset = []

        for task in self.series_tasks:
            submission = task_submissions.get(task.id)

            formset.append(
                (
                    task,
                    forms.SolutionSubmitForm(
                        files=self.request.FILES
                        if self.request.method == "POST"
                        and str(task.id) == form_task_id
                        else None,
                        task=task,
                    )
                    if task.id not in task_submissions
                    else None,
                    submission,
                    submission.can_delete(self.request.user) if submission else False,
                )
            )

        return formset

    def post(self, request, *args, **kwargs):
        forms = self.get_forms()

        for task, form, _, _ in forms:
            if form is not None and form.is_valid():
                self.save_solution(task)
                return redirect("core:solution_submit")

        return self.render_to_response(self.get_context_data(forms=forms))

    @transaction.atomic
    def save_solution(self, task):
        """Create new solution submissions for given files."""
        file_descriptor = self.request.FILES.get(f"file_{task.pk}")

        if not file_descriptor:
            raise ValueError("Could not locate submitted file")

        submission, created = TaskSolutionSubmission.objects.get_or_create(
            application=self.application,
            task=task,
            defaults={"file": file_descriptor},
        )

        if not created:
            messages.add_message(
                self.request,
                messages.WARNING,
                f"<i class='fas fa-exclamation-circle notification-icon'></i> Řešení pro úlohu {task} již bylo dříve odevzdáno.",
            )
            return

        submission.prepare_for_export()
        submission.save()

        messages.add_message(
            self.request,
            messages.SUCCESS,
            f"<i class='fas fa-check-circle notification-icon'></i> Řešení úlohy {task} bylo <strong>úspěšně odesláno</strong>.",
        )


class SolutionSubmitDeleteView(DeleteView):
    model = TaskSolutionSubmission
    context_object_name = "task"
    success_url = reverse_lazy("core:solution_submit")

    def delete(self, request, *args, **kwargs):
        object = self.get_object()

        if object.can_delete(self.request.user):
            messages.add_message(
                self.request,
                messages.SUCCESS,
                f"<i class='fas fa-check-circle notification-icon'></i> Řešení úlohy {object.task.title} bylo <strong>smazáno</strong>.",
            )
            return super().delete(request, *args, **kwargs)

        messages.add_message(
            self.request,
            messages.WARNING,
            "<i class='fas fa-exclamation-circle notification-icon'></i> Toto řešení momentálně nemůžeš smazat.",
        )
        return redirect("core:solution_submit")

    def render_to_response(self, context, **response_kwargs):
        if self.object.can_delete(self.request.user):
            return super().render_to_response(context, **response_kwargs)

        return redirect("core:solution_submit")


@method_decorator(
    [permission_required("core.change_solution_submission_presence")], name="dispatch"
)
class SubmissionOverview(FormView):
    form_class = formset_factory(
        forms.SubmissionForm, formset=forms.SubmissionOverviewFormSet, extra=0
    )
    template_name = "core/manage/submission_overview.html"

    def dispatch(self, *args, grade_id, series_id, **kwargs):
        self.grade = Grade.objects.filter(id=grade_id).first()
        self.series = GradeSeries.objects.filter(grade=self.grade, pk=series_id).first()

        if not self.grade or not self.series:
            return HttpResponseNotFound()

        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["grade"] = self.grade
        context["series"] = self.series
        return context

    def get_form_kwargs(self):
        participants = (
            Participant.objects.filter(applications__series=self.series)
            .select_related("user")
            .order_by("user__last_name", "user__first_name", "user__email")
        )
        tasks = Task.objects.filter(series=self.series)

        submission_map = {}

        for participant in participants:
            submission_map[participant.user_id] = OrderedDict()

            for task in tasks:
                submission_map[participant.user_id][task.id] = None

        for s in TaskSolutionSubmission.objects.filter(
            application__grade=self.grade,
            task__series=self.series,
        ).select_related("task", "application"):
            submission_map[s.application.participant_id][s.task.id] = s

        def _build_initial(participant):
            i = {"participant": participant.user_id}

            for task_id, submission in submission_map[participant.user_id].items():
                i[f"task_{task_id}"] = bool(submission)

            return i

        return {
            **super().get_form_kwargs(),
            "initial": {
                i: _build_initial(participant)
                for i, participant in enumerate(participants)
            },
            "form_kwargs": {
                str(i): {
                    "participant": participant,
                    "digital_submissions": [
                        s.task_id
                        for s in submission_map[participant.user_id].values()
                        if (bool(s) and bool(s.file))
                    ],
                    "tasks": tasks,
                }
                for i, participant in enumerate(participants)
            },
        }

    def form_valid(self, form):
        submissions = TaskSolutionSubmission.objects.filter(
            application__grade=self.grade,
            task__series=self.series,
        )
        applications = GradeApplication.objects.filter(grade=self.grade)

        # Map participant_id -> application_id
        application_map = {a.participant_id: str(a.id) for a in applications}

        # Saved submissions come from DB, triplets (application_id, task_id, should_exist)
        saved_submissions = {
            (application_map[s.application.participant_id], str(s.task_id), True)
            for s in submissions
        }
        desired_submissions = set()

        for cdi in form.cleaned_data:
            participant_id = cdi["participant"]

            for field_name, field_value in cdi.items():
                if field_name != "participant":
                    _, task_id = field_name.split("_")
                    desired_submissions.add(
                        (application_map[participant_id], task_id, field_value)
                    )

        missing_submissions = desired_submissions - saved_submissions
        overdue_submissions = saved_submissions - desired_submissions

        to_create = []

        # Handle submissions to create
        for s in missing_submissions:
            app_id, task_id, should_exist = s

            if should_exist:
                to_create.append(
                    TaskSolutionSubmission(application_id=app_id, task_id=task_id)
                )

        TaskSolutionSubmission.objects.bulk_create(to_create)

        # Handle submissions to delete
        filtering = []
        for s in overdue_submissions:
            app_id, task_id, _ = s
            filtering.append(models.Q(application_id=app_id, task_id=task_id))

        if len(filtering) > 0:
            TaskSolutionSubmission.objects.filter(reduce(or_, filtering)).delete()

        messages.add_message(
            self.request,
            messages.SUCCESS,
            "<i class='fas fa-check-circle notification-icon'></i> Odevzdaná řešení byla uložena.",
        )

        return redirect(".")


@method_decorator([permission_required("core.scoring")], name="dispatch")
class ScoringView(FormView):
    template_name = "core/manage/scoring.html"
    form_class = modelformset_factory(
        TaskSolutionSubmission,
        form=forms.ScoringForm,
        fields=("id", "score", "stickers"),
        extra=0,
    )

    def dispatch(self, *args, task_id, **kwargs):
        self.task = get_object_or_404(
            Task.objects.select_related("series__grade"), id=task_id
        )
        return super().dispatch(*args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["task"] = self.task
        return context

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "queryset": TaskSolutionSubmission.objects.filter(task=self.task)
            .select_related("application__participant__user")
            .prefetch_related("stickers")
            .order_by(
                "application__participant__user__last_name",
                "application__participant__user__first_name",
            ),
            "form_kwargs": {
                "max_score": self.task.points,
                "sticker_choices": Sticker.objects.filter(handpicked=True).order_by(
                    "nr"
                ),
            },
        }

    def form_valid(self, form):
        form.save()

        messages.add_message(
            self.request,
            messages.SUCCESS,
            "<i class='fas fa-check-circle notification-icon'></i> Bodování bylo uloženo.",
        )

        return redirect(".")


@method_decorator([permission_required("core.scoring")], name="dispatch")
class SolutionExportView(View):
    def dispatch(self, *args, task_id, **kwargs):
        self.task = get_object_or_404(Task, id=task_id)
        return super().dispatch(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        submitted_solutions = (
            TaskSolutionSubmission.objects.filter(task=self.task)
            .select_related("task", "application__participant__user")
            .exclude(file="")
            .order_by(
                "application__participant__user__last_name",
                "application__participant__user__first_name",
            )
        )
        submitted_solutions = [s for s in submitted_solutions if bool(s.file)]

        if len(submitted_solutions) == 0:
            messages.add_message(
                self.request,
                messages.WARNING,
                "<i class='fas fa-exclamation-circle notification-icon'></i> Žádné řešení neobsahuje přiložené soubory.",
            )
            return redirect(
                reverse(
                    "core:series_detail",
                    kwargs={
                        "grade_id": self.task.series.grade_id,
                        "pk": self.task.series.pk,
                    },
                )
            )

        response = HttpResponse(content_type="application/pdf")
        filename = quote(f"{self.task} - export řešení")
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}.pdf"
        is_duplex = bool(request.GET.get("duplex"))
        solution_files = []

        for s in submitted_solutions:
            solution_files.append(
                s.file_for_export_normal
            )

        # Join all files in one large batch.
        pdf.concatenate(solution_files, response, is_duplex)

        return response

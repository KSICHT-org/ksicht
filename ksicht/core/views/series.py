from collections import defaultdict

from django.views.generic.detail import DetailView
from django.shortcuts import redirect
from django.contrib import messages

from .. import models
from ..sticker_utils import get_sticker_display_info, is_assignment_in_series
from ksicht.core.stickers.services import grant_stickers_for_series


__all__ = (
    "SeriesDetailView",
    "SeriesResultsView",
    "StickerAssignmentOverview",
)


class SeriesDetailView(DetailView):
    queryset = models.GradeSeries.objects.all()
    template_name = "core/manage/series_detail.html"


class SeriesResultsView(DetailView):
    template_name = "core/series_results.html"
    queryset = (
        models.GradeSeries.objects.filter(results_published=True)
        .select_related("grade")
        .prefetch_related("tasks")
    )

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        series = data["object"]

        # Determine if this is the last series in the grade
        all_series = list(
            models.GradeSeries.objects.filter(grade=series.grade).order_by("series")
        )
        is_last_series = len(all_series) > 0 and series == all_series[-1]
        data["is_last_series"] = is_last_series

        if is_last_series:
            rankings = series.get_rankings()
            max_score = rankings["max_score"] or 0
            successful_ids = set()

            for application, rank, task_scores, total_score in rankings["listing"]:
                if total_score >= max_score * 0.5 or rank <= 30:
                    successful_ids.add(application.pk)

            data["successful_application_ids"] = successful_ids

        # Compute rank and score changes from the previous series
        current_index = next(
            (i for i, s in enumerate(all_series) if s == series), 0
        )
        data["has_previous_series"] = current_index > 0
        if current_index > 0:
            prev_series = all_series[current_index - 1]
            prev_rankings = prev_series.get_rankings()
            prev_by_app = {
                app.pk: (rank, total_score)
                for app, rank, _, total_score in prev_rankings["listing"]
            }

            current_rankings = series.get_rankings()
            rank_changes = {}
            score_changes = {}
            for application, rank, _, total_score in current_rankings["listing"]:
                prev_data = prev_by_app.get(application.pk)
                if prev_data is not None:
                    prev_rank, prev_score = prev_data
                    rank_changes[application.pk] = prev_rank - rank  # positive = moved up
                    score_changes[application.pk] = total_score - prev_score
            data["rank_changes"] = rank_changes
            data["score_changes"] = score_changes

        return data


class StickerAssignmentOverview(DetailView):
    template_name = "core/manage/sticker_assignment_overview.html"
    queryset = models.GradeSeries.objects.all().select_related("grade")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        grant_stickers_for_series(self.object)

        messages.success(
            request,
            f"<i class='fas fa-check-circle notification-icon'></i> Nálepky pro sérii {self.object} byly úspěšně přepočítány."
        )
        return redirect("core:series_sticker_assignment_overview", grade_id=self.object.grade_id, pk=self.object.id)

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        series = data["object"]
        grade = series.grade

        applications = (
            models.GradeApplication.objects.filter(grade=series.grade_id)
            .select_related("participant__user")
            .order_by(
                "participant__user__last_name",
                "participant__user__first_name",
                "participant__user__email",
            )
        )

        participant_ids = [a.participant_id for a in applications]

        # Fetch all assignments for these participants
        all_assignments = list(models.StickerAssignment.objects.filter(
            participant_id__in=participant_ids
        ).select_related(
            "sticker", "awarded_in_series",
            "awarded_for_submission__task__series",
            "awarded_for_event"
        ))

        sticker_cache = {s.nr: s for s in models.Sticker.objects.all()}
        sticker_limits = {
            s.nr: s.assignment_limit
            for s in sticker_cache.values()
        }

        # Organize assignments by participant
        assignments_by_participant = defaultdict(list)
        for a in all_assignments:
            assignments_by_participant[a.participant_id].append(a)

        # Run eligibility engine to find which stickers each participant WOULD earn
        from ksicht.core.stickers.engine import get_eligibility
        eligibility = get_eligibility(series)
        eligible_by_participant = {}
        for application, sticker_nrs in eligibility:
            eligible_by_participant[application.participant_id] = sticker_nrs

        def _collect_stickers(application):
            pid = application.participant_id
            participant_assignments = assignments_by_participant[pid]
            eligible_nrs = eligible_by_participant.get(pid, [])

            # 1. Collect stickers actually assigned in this series (solid tags)
            assigned_in_series = [
                a for a in participant_assignments
                if is_assignment_in_series(a, grade, series)
            ]

            result = []
            grayed_list = []
            seen_nrs = set()

            for a in sorted(assigned_in_series, key=lambda x: x.sticker.nr):
                if a.sticker.nr in seen_nrs:
                    continue
                seen_nrs.add(a.sticker.nr)

                grayed_out, limit_label = get_sticker_display_info(
                    a, grade, series, participant_assignments, sticker_limits
                )

                if grayed_out:
                    grayed_list.append((a.sticker, grayed_out, limit_label, a.assigned_after_publication))
                else:
                    result.append((a.sticker, False, "", a.assigned_after_publication))

            # 2. For eligible stickers NOT assigned in this series, check if
            #    they're limited (already awarded elsewhere) → show as light tags
            for nr in eligible_nrs:
                if nr in seen_nrs:
                    continue
                sticker = sticker_cache.get(nr)
                if not sticker or sticker.handpicked:
                    continue

                limit = sticker_limits.get(nr, "unlimited")
                if limit == "unlimited":
                    # Unlimited sticker not assigned → skip (shouldn't normally happen)
                    continue

                # Find prior assignments of this sticker (not in current series)
                prior_assignments = [
                    a for a in participant_assignments
                    if a.sticker_id == sticker.id and not is_assignment_in_series(a, grade, series)
                ]

                if not prior_assignments:
                    continue

                # Check if any prior assignment was made after publication
                any_after_pub = any(a.assigned_after_publication for a in prior_assignments)

                if limit == "once_in_lifetime":
                    grayed_list.append((sticker, True, "Již udělena dříve", any_after_pub))
                elif limit == "once_per_grade":
                    # Check if prior assignment is from the same grade
                    same_grade_assignments = [
                        a for a in prior_assignments
                        if a.awarded_in_series_id
                        and a.awarded_in_series.grade_id == grade.id
                    ]
                    if same_grade_assignments:
                        any_after_pub_grade = any(a.assigned_after_publication for a in same_grade_assignments)
                        grayed_list.append((sticker, True, "Již udělena v tomto ročníku", any_after_pub_grade))

                    seen_nrs.add(nr)

            return {"eligible": result, "grayed": grayed_list}

        data["results"] = {a: _collect_stickers(a) for a in applications}
        return data


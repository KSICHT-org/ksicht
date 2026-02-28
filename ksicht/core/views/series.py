from operator import attrgetter

from django.views.generic.detail import DetailView
import pydash as py_

from .. import models, stickers


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


def sticker_nrs_to_objects(listing):
    """Replace sticker numbers in eligibility listing with real sticker objects."""
    sticker_nrs = (
        py_.py_(list(nrs) for application, nrs in listing).flatten().uniq().value()
    )
    stickers_by_nr = {
        s.nr: s for s in models.Sticker.objects.filter(nr__in=sticker_nrs)
    }

    def _replace_with_sticker_objs(listing_item):
        application, sticker_nrs = listing_item
        return (
            application,
            [stickers_by_nr[nr] for nr in sticker_nrs if nr in stickers_by_nr],
        )

    return dict([_replace_with_sticker_objs(l) for l in listing])


def get_event_stickers(series):
    """Resolve stickers to be collected from events.

    These are assigned to everyone who attended (not to substitutes).
    """
    prev_series = (
        models.GradeSeries.objects.filter(
            grade=series.grade, submission_deadline__lte=series.submission_deadline
        )
        .exclude(pk=series.pk)
        .order_by("-submission_deadline", "-pk")
        .first()
    )
    related_events = models.Event.objects.filter(
        start_date__gte=(
            prev_series.submission_deadline if prev_series else series.grade.start_date
        ),
        end_date__lte=series.submission_deadline,
    ).prefetch_related("reward_stickers", "attendees")

    return [(e, e.reward_stickers.all()) for e in related_events]


class StickerAssignmentOverview(DetailView):
    template_name = "core/manage/sticker_assignment_overview.html"
    queryset = models.GradeSeries.objects.all().select_related("grade")

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        series = data["object"]
        applications = (
            models.GradeApplication.objects.filter(grade=series.grade_id)
            .select_related("participant__user")
            .order_by(
                "participant__user__last_name",
                "participant__user__first_name",
                "participant__user__email",
            )
        )

        series_submissions = models.TaskSolutionSubmission.objects.filter(
            task__series=series
        ).prefetch_related("stickers")
        auto_stickers = sticker_nrs_to_objects(stickers.engine.get_eligibility(series))
        event_stickers = get_event_stickers(series)

        def _collect_stickers(application):
            stickers = set(auto_stickers[application])

            for event, stickers_from_event in event_stickers:
                user = application.participant.user

                # Only add event stickers to real attendees, not substitutes.
                if user in event.attendees.all()[: event.capacity]:
                    stickers = stickers.union(set(stickers_from_event))

            application_submissions = [
                s for s in series_submissions if s.application_id == application.pk
            ]

            for s in application_submissions:
                stickers = stickers.union(set(s.stickers.all()))

            return sorted(stickers, key=attrgetter("nr"))

        data["results"] = {a: _collect_stickers(a) for a in applications}
        return data

from decimal import Decimal
from typing import List, Set, Tuple

from . import registry, types
from .. import models


def resolve_stickers(context: types.StickerContext):
    """Get set of stickers where provided context resolves truthy."""
    entitled_to: Set[int] = set()

    for sticker_nr, sticker_resolver in registry.get_all():
        if sticker_resolver(context):
            entitled_to.add(sticker_nr)

    return entitled_to


def _grade_details(grade: models.Grade) -> types.GradeDetails:
    """Get details of the grade."""
    applications = list(
        grade.applications.order_by("created_at").select_related("participant__user")
    )
    series = list(
        models.GradeSeries.objects.filter(grade=grade)
        .order_by("series")
        .select_related("grade")
    )
    tasks = list(models.Task.objects.filter(series__grade=grade))
    submitted_solutions = list(models.TaskSolutionSubmission.objects.filter(
        task__series__grade=grade
    ).select_related("task__series"))

    # Optimization: Group submissions by application PK once
    submissions_by_app = {}
    for s in submitted_solutions:
        submissions_by_app.setdefault(s.application_id, []).append(s)

    # Optimization: Pre-calculate rankings for all series and map them by application PK
    rankings_by_series = {}
    for s in series:
        # Calculate max_score for this series (including previous ones) in memory
        current_series_max_score = sum(
            t.points for t in tasks 
            if int(t.series.series) <= int(s.series)
        )

        r = s.get_rankings(
            _applications_cache=applications,
            _tasks_cache=[t for t in tasks if t.series_id == s.pk],
            _submissions_cache=submitted_solutions,
            _max_score=current_series_max_score,
        )
        # Create a fast lookup map for this series: app_pk -> (rank, score)
        r_map = {row[0].pk: (row[1], row[3]) for row in r["listing"]}
        rankings_by_series[s.pk] = {
            "max_score": r["max_score"],
            "map": r_map
        }

    grade_details: types.GradeDetails = {
        "series": series,
        "tasks": {s: [t for t in tasks if t.series_id == s.pk] for s in series},
        "by_participant": {},
    }

    for application in applications:
        submissions = submissions_by_app.get(application.pk, [])
        
        # Pre-build series details for this participant
        participant_series_details = {}
        for s in series:
            r_info = rankings_by_series[s.pk]
            app_ranking = r_info["map"].get(application.pk, (None, Decimal("0")))
            participant_series_details[s] = {
                "rank": app_ranking[0],
                "score": app_ranking[1],
                "max_score": r_info["max_score"],
            }

        # Pre-map submissions by task for faster lookup in by_tasks
        submissions_by_task = {s.task_id: s for s in submissions}

        grade_details["by_participant"][application.participant] = {
            "series": participant_series_details,
            "submissions": {
                "all": submissions,
                "by_series": {
                    s: [sub for sub in submissions if sub.task.series_id == s.pk]
                    for s in series
                },
                "by_tasks": {
                    t: submissions_by_task.get(t.pk)
                    for t in tasks
                },
            },
        }

    return grade_details


def get_eligibility(current_series: models.GradeSeries, _grade_details_cache: dict = None):
    """Find out sticker eligibility for every participant in the series."""
    if _grade_details_cache is None:
        _grade_details_cache = {}

    def _get_cached_details(g):
        if g.pk not in _grade_details_cache:
            _grade_details_cache[g.pk] = _grade_details(g)
        return _grade_details_cache[g.pk]

    current_grade = current_series.grade
    grades = [current_grade]
    grades.extend(
        models.Grade.objects.filter(start_date__lt=current_grade.start_date).order_by(
            "-end_date"
        )[:3]
    )
    applications: List[models.GradeApplication] = list(
        current_grade.applications.select_related("participant__user")
    )
    base_context = {
        "by_grades": {grades.index(grade): _get_cached_details(grade) for grade in grades}
    }
    eligibility: List[Tuple[models.GradeApplication, Set[int]]] = []
    current_grade_details = base_context["by_grades"][0]

    for application in applications:
        context: types.StickerContext = {
            "participant": application.participant,
            "current": {
                "participant": current_grade_details["by_participant"][
                    application.participant
                ],
                "grade": current_grade_details,
                "series": current_series,
                "is_last_series": len(current_grade_details["series"]) > 0
                and current_series == current_grade_details["series"][-1],
            },
            **base_context,
        }

        eligibility.append((application, resolve_stickers(context)))

    return eligibility

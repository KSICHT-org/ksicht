"""
Shared utility functions for sticker display logic.
Centralizes the "is this sticker grayed out?" check used by multiple views.
"""

from datetime import datetime

from ksicht.core import models


def get_sticker_display_info(assignment, grade, series, all_assignments, sticker_limits):
    """
    Determine if a sticker assignment should be displayed as grayed out (light variant).

    Args:
        assignment: The StickerAssignment being displayed.
        grade: The Grade this display belongs to.
        series: The GradeSeries this display belongs to.
        all_assignments: All StickerAssignment records for this participant (pre-fetched).
        sticker_limits: Dict mapping sticker.nr -> assignment_limit value.

    Returns:
        (grayed_out: bool, limit_label: str)
    """
    sticker = assignment.sticker
    limit = sticker_limits.get(sticker.nr, "unlimited")

    if assignment.ignore_limit or limit == "unlimited":
        return False, ""

    # Check if there's an earlier assignment of the same sticker
    for a in all_assignments:
        if a.sticker_id != sticker.id or a.id == assignment.id:
            continue
        if a.ignore_limit:
            continue

        # Get the series this earlier assignment belongs to
        a_series = _get_assignment_series(a)
        current_series_deadline = series.submission_deadline

        if a_series and a_series.submission_deadline < current_series_deadline:
            if limit == "once_in_lifetime":
                return True, "Již udělena dříve"
            elif limit == "once_per_grade" and a_series.grade_id == grade.id:
                return True, "Již udělena v tomto ročníku"

    return False, ""


def _get_assignment_series(assignment):
    """Get the GradeSeries associated with an assignment, if any."""
    if assignment.awarded_in_series_id:
        return assignment.awarded_in_series
    elif assignment.awarded_for_submission_id:
        return assignment.awarded_for_submission.task.series
    return None


def get_assignment_series_id(assignment, grade, series):
    """
    Determine if an assignment belongs to a specific series.
    Returns True if the assignment is associated with the given series.
    """
    if assignment.awarded_in_series_id == series.id:
        return True
    if assignment.awarded_for_submission_id:
        return assignment.awarded_for_submission.task.series_id == series.id
    if assignment.awarded_for_event_id:
        event = assignment.awarded_for_event
        prev_series = models.GradeSeries.objects.filter(
            grade=grade,
            submission_deadline__lt=series.submission_deadline
        ).order_by("-submission_deadline").first()
        since = prev_series.submission_deadline if prev_series else grade.start_date
        since_date = since.date() if isinstance(since, datetime) else since
        if since_date <= event.start_date < series.submission_deadline.date():
            return True
    return False

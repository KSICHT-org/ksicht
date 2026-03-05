import logging
from typing import Dict, List, Set, Tuple

from django.db import transaction

from ksicht.core import models
from .engine import get_eligibility

logger = logging.getLogger(__name__)


def _is_limit_reached(participant_id, sticker, current_series, assignment_cache_map) -> bool:
    """
    Check if the participant has already reached the assignment limit for this sticker.
    Uses pre-fetched assignment cache for efficiency.
    Only considers assignments BEFORE the current series (not in the current series itself).
    """
    if sticker.assignment_limit == models.Sticker.AssignmentLimit.UNLIMITED:
        return False

    assignments = assignment_cache_map.get((participant_id, sticker.id), [])
    if not assignments:
        return False

    if sticker.assignment_limit == models.Sticker.AssignmentLimit.ONCE_IN_LIFETIME:
        # Any prior assignment (not in current series) means limit reached
        for a in assignments:
            if a.awarded_in_series_id != current_series.id:
                return True
        return False

    if sticker.assignment_limit == models.Sticker.AssignmentLimit.ONCE_PER_GRADE and current_series:
        for a in assignments:
            # Skip assignments from the current series itself
            if a.awarded_in_series_id == current_series.id:
                continue
            # Check if this assignment is from the same grade
            a_grade_id = None
            if a.awarded_in_series_id:
                a_grade_id = a.awarded_in_series.grade_id
            elif a.awarded_for_submission_id:
                a_grade_id = a.awarded_for_submission.task.series.grade_id

            if a_grade_id == current_series.grade_id:
                return True

    return False


def get_event_stickers(series: models.GradeSeries):
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


@transaction.atomic
def grant_stickers_for_series(series: models.GradeSeries, *, skip_limits=False):
    """
    Evaluates eligibility for a single series and syncs auto sticker assignments.

    Behavior depends on results_published:
    - Before publication: full sync (add missing + remove invalid auto stickers)
    - After publication: additive only (add missing, never remove)

    Never touches:
    - Historical assignments (ignore_limit=True)
    - Event sticker assignments
    - Manual submission sticker assignments (handpicked)
    """
    logger.info("Granting stickers for %s (published=%s, skip_limits=%s)", series, series.results_published, skip_limits)

    sticker_cache = {s.nr: s for s in models.Sticker.objects.all()}
    eligibility = get_eligibility(series)

    # Get all participants in this series
    participants = [app.participant for app, _ in eligibility]
    participant_ids = [p.pk for p in participants]

    # Build assignment cache: all non-ignore_limit assignments for these participants
    raw_assignments = models.StickerAssignment.objects.filter(
        participant_id__in=participant_ids,
        ignore_limit=False
    ).select_related(
        "sticker", "awarded_in_series__grade",
        "awarded_for_submission__task__series__grade"
    )
    assignment_cache_map: Dict[Tuple, List] = {}
    for a in raw_assignments:
        key = (a.participant_id, a.sticker_id)
        assignment_cache_map.setdefault(key, []).append(a)

    # Get ALL existing assignments for THIS series (for duplicate detection)
    all_existing_for_series = set(
        models.StickerAssignment.objects.filter(
            awarded_in_series=series,
        ).values_list("participant_id", "sticker_id")
    )

    # Get only removable (non-historical) assignments for this series
    removable_for_series = set(
        models.StickerAssignment.objects.filter(
            awarded_in_series=series,
            ignore_limit=False,
        ).values_list("participant_id", "sticker_id")
    )

    new_assignments = []
    should_exist: Set[Tuple] = set()  # (participant_id, sticker_id) pairs that SHOULD exist

    # Process auto stickers from eligibility engine
    for application, sticker_nrs in eligibility:
        pid = application.participant_id
        for nr in sticker_nrs:
            sticker = sticker_cache.get(nr)
            if not sticker:
                continue
            # Skip handpicked stickers — they're managed manually via the scoring form
            if sticker.handpicked:
                continue

            should_exist.add((pid, sticker.id))

            if skip_limits or not _is_limit_reached(pid, sticker, series, assignment_cache_map):
                key = (pid, sticker.id)
                # Check if already exists in this specific series (including historical)
                already_exists = (pid, sticker.id) in all_existing_for_series
                if not already_exists:
                    assignment = models.StickerAssignment(
                        participant_id=pid,
                        sticker=sticker,
                        awarded_in_series=series,
                        assigned_after_publication=series.results_published and not skip_limits,
                    )
                    new_assignments.append(assignment)
                    # Update cache so limit checks within same run are accurate
                    assignment_cache_map.setdefault(key, []).append(assignment)

    # Assign event stickers
    event_stickers = get_event_stickers(series)
    for event, stickers_from_event in event_stickers:
        attendee_users = [a.id for a in event.attendees.all()[: event.capacity]]
        relevant_participants = models.Participant.objects.filter(
            user_id__in=attendee_users
        ).select_related('user')

        for participant in relevant_participants:
            for sticker in stickers_from_event:
                if skip_limits or not _is_limit_reached(participant.pk, sticker, series, assignment_cache_map):
                    key = (participant.pk, sticker.id)
                    exists_locally = any(
                        a.awarded_for_event_id == event.id
                        for a in assignment_cache_map.get(key, [])
                    )
                    if not exists_locally:
                        assignment = models.StickerAssignment(
                            participant_id=participant.pk,
                            sticker=sticker,
                            awarded_for_event=event,
                            assigned_after_publication=series.results_published and not skip_limits,
                        )
                        new_assignments.append(assignment)
                        assignment_cache_map.setdefault(key, []).append(assignment)

    # Create new assignments
    if new_assignments:
        models.StickerAssignment.objects.bulk_create(new_assignments, ignore_conflicts=True)

    # Remove invalid auto stickers ONLY if results not yet published
    if not series.results_published:
        # Find auto assignments that exist but shouldn't (participant no longer eligible)
        # Only consider non-handpicked, non-event, non-ignore_limit assignments
        to_remove = removable_for_series - should_exist

        if to_remove:
            # Build Q filter for deletion — only delete auto (awarded_in_series) assignments
            for pid, sid in to_remove:
                sticker = next((s for s in sticker_cache.values() if s.id == sid), None)
                if sticker and not sticker.handpicked:
                    models.StickerAssignment.objects.filter(
                        participant_id=pid,
                        sticker_id=sid,
                        awarded_in_series=series,
                        ignore_limit=False,
                    ).delete()
            logger.info("Removed %d invalid auto stickers for %s", len(to_remove), series)

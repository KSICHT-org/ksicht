from datetime import timedelta
from decimal import Decimal
import heapq
import math
import random

from . import registry
from .types import GradeDetails, StickerContext


def sticker(sticker_nr):
    def decorator(resolver_fn):
        registry.register(sticker_nr, resolver_fn)
        return resolver_fn

    return decorator


@sticker(1)
def solver(context: StickerContext):
    """Given to anyone who participates."""
    return True


@sticker(2)
def solved_all_tasks_in_series(context: StickerContext):
    """Given to anyone who has submitted solutions for all tasks of current series."""
    current_series = context["current"]["series"]
    participant_submissions = context["current"]["participant"]["submissions"]
    tasks = context["current"]["grade"]["tasks"][current_series]
    return len(tasks) > 0 and len(
        participant_submissions["by_series"][current_series]
    ) == len(tasks)


@sticker(3)
def solution_in_every_series(context: StickerContext):
    """Given to anyone who has submitted a solution in every series."""
    return context["current"]["is_last_series"] and all(
        len(submissions) != 0
        for submissions in context["current"]["participant"]["submissions"][
            "by_series"
        ].values()
    )


@sticker(4)
def solved_all_tasks(context: StickerContext):
    """Given to anyone who has submitted solutions for every task."""
    return context["current"]["is_last_series"] and all(
        sub is not None
        for sub in context["current"]["participant"]["submissions"]["by_tasks"].values()
    )


@sticker(8)
def zero_points(context: StickerContext):
    """Given to anyone who has been given 0 score points in any of the submitted solutions within a series."""
    return any(
        sub.score == Decimal("0")
        for sub in context["current"]["participant"]["submissions"]["by_series"][
            context["current"]["series"]
        ]
    )


@sticker(9)
def reached_100(context: StickerContext):
    """Given to anyone who has reached a sum of at least 100 points."""
    return sum(
        sub.score or Decimal("0")
        for sub in context["current"]["participant"]["submissions"]["all"]
    ) >= Decimal("100")


@sticker(10)
def reached_150(context: StickerContext):
    """Given to anyone who has reached a sum of at least 150 points."""
    return sum(
        sub.score or Decimal("0")
        for sub in context["current"]["participant"]["submissions"]["all"]
    ) >= Decimal("150")


@sticker(12)
def full_score(context: StickerContext):
    """Given to anyone who has been given the maximum number of points for at least one of their submissions within a series."""
    current_series = context["current"]["series"]
    tasks = context["current"]["grade"]["tasks"][current_series]

    def _is_eligible(submission):
        task = next(t for t in tasks if submission.task_id == t.pk)
        return task.points == submission.score

    return any(
        _is_eligible(sub)
        for sub in context["current"]["participant"]["submissions"]["by_series"][
            current_series
        ]
    )


@sticker(13)
def random_2_percent(context: StickerContext):
    """Randomly (yet with predictable seed according to current_series) given to approx 2% of the applications."""
    applications_count = len(context["current"]["grade"]["by_participant"])
    pick_count = math.ceil(applications_count * 0.02)

    # Initialize seed for the randomness to be consistent with current_series
    random.seed(int(context["current"]["series"].pk))

    return context["participant"].pk in random.choices(
        [a.pk for a in context["current"]["grade"]["by_participant"]], k=pick_count
    )


@sticker(14)
def late_submission(context: StickerContext):
    """Given to max 10 participants who submitted their solutions within 30 minutes of the deadline."""
    current_series = context["current"]["series"]

    def _is_eligible(submission):
        ## checks whether file is provided, e.g. was submitted digitally
        return bool(submission.file) and (
            current_series.submission_deadline - submission.submitted_at
        ) <= timedelta(hours=4)

    latest_submissions = []

    # iterates over all participants as they are already prefetched
    for participant, details in context["current"]["grade"]["by_participant"].items():
        submissions = details["submissions"]["by_series"].get(current_series, [])
        eligible_submissions = [sub for sub in submissions if _is_eligible(sub)]

        if eligible_submissions:
            latest_time = max(sub.submitted_at for sub in eligible_submissions)
            latest_submissions.append((latest_time, participant.pk))

    top_10_submissions = heapq.nlargest(10, latest_submissions, key=lambda x: x[0])

    most_recent_10_pks = {pk for _, pk in top_10_submissions}

    return context["participant"].pk in most_recent_10_pks


@sticker(15)
def early_submission(context: StickerContext):
    """Given to anyone who has submitted a solution in series more than 2 weeks before submission deadline."""
    current_series = context["current"]["series"]

    def _is_submission_eligible(submission):
        return (
            current_series.submission_deadline - submission.submitted_at
        ) >= timedelta(days=14)

    submissions = context["current"]["participant"]["submissions"]["by_series"][
        current_series
    ]

    return len(submissions) > 0 and all(
        _is_submission_eligible(sub) for sub in submissions
    )


@sticker(18)
def ranked_no_worse_than_7th(context: StickerContext):
    """Given to anyone who has ranked no worse than 7th in all of the series of grades."""
    if not context["current"]["is_last_series"]:
        return False

    return all(
        cs["rank"] <= 7 for cs in context["current"]["participant"]["series"].values()
    )


@sticker(19)
def successfull_solver(context: StickerContext):
    """Given to anyone who has got at least 50% of the points or has ranked 30th or less in the last series."""
    participant_details = context["current"]["participant"]["series"][
        context["current"]["series"]
    ]

    return context["current"]["is_last_series"] and (
        (participant_details["score"] >= participant_details["max_score"] * 0.5)
        or (participant_details["rank"] <= 30)
    )


@sticker(29)
def submitted_solution_in_last_series(context: StickerContext):
    """Given to anyone who has submitted a solution in last series of the grade."""
    current_series = context["current"]["series"]

    return (
        context["current"]["is_last_series"]
        and len(
            context["current"]["participant"]["submissions"]["by_series"][
                current_series
            ]
        )
        > 0
    )


def submitted_solution_in_each_task_of_last_n_grades(context: StickerContext, n: int):
    participant = context["participant"]

    def _is_eligible(grade: GradeDetails):
        tasks_count = sum(len(tasks) for tasks in grade["tasks"].values())

        if participant in grade["by_participant"]:
            submission_count = len(
                grade["by_participant"][participant]["submissions"]["all"]
            )
        else:
            submission_count = 0

        return tasks_count == submission_count

    last_n_grades = list(context["by_grades"].values())[:n]

    return (
        context["current"]["is_last_series"]
        and len(last_n_grades) == n
        and all(_is_eligible(grade) for grade in last_n_grades)
    )


@sticker(35)
def submitted_solution_in_each_task_of_last_two_grades(context: StickerContext):
    """Given to anyone who has submitted a solution in each task of last two grades."""
    return submitted_solution_in_each_task_of_last_n_grades(context, 2)


@sticker(36)
def submitted_solution_in_each_task_of_last_three_grades(context: StickerContext):
    """Given to anyone who has submitted a solution in each task of last three grades."""
    return submitted_solution_in_each_task_of_last_n_grades(context, 3)


@sticker(37)
def submitted_solution_in_each_task_of_last_four_grades(context: StickerContext):
    """Given to anyone who has submitted a solution in each task of last four grades."""
    return submitted_solution_in_each_task_of_last_n_grades(context, 4)


@sticker(38)
def fellowship_of_benzenes(context: StickerContext):
    """Given to anyone who has ranked no worse than 6th in the last series."""
    return (
        context["current"]["participant"]["series"][context["current"]["series"]][
            "rank"
        ]
        <= 6
    )


@sticker(42)
def ranked_42nd(context: StickerContext):
    """Given to anyone who has ranked 42nd in the current series."""
    return (
        context["current"]["participant"]["series"][context["current"]["series"]][
            "rank"
        ]
        == 42
    )

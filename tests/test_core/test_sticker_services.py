from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ksicht.core import models
from ksicht.core.stickers.services import grant_stickers_for_series


pytestmark = [pytest.mark.django_db]


@pytest.fixture
def grade():
    return models.Grade.objects.create(
        school_year="19/20",
        start_date=datetime(2020, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2020, 12, 31, tzinfo=timezone.utc),
    )


@pytest.fixture
def grade2():
    return models.Grade.objects.create(
        school_year="20/21",
        start_date=datetime(2021, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2021, 12, 31, tzinfo=timezone.utc),
    )


@pytest.fixture
def series1(grade):
    return models.GradeSeries.objects.create(
        grade=grade,
        series="1",
        submission_deadline=datetime(2020, 2, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def series2(grade):
    return models.GradeSeries.objects.create(
        grade=grade,
        series="2",
        submission_deadline=datetime(2020, 4, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def series1_grade2(grade2):
    return models.GradeSeries.objects.create(
        grade=grade2,
        series="1",
        submission_deadline=datetime(2021, 2, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def task1(series1):
    return models.Task.objects.create(series=series1, nr=1, points=Decimal("100.0"))


@pytest.fixture
def participant():
    user = models.User.objects.create(
        email="test@example.com", first_name="Test", last_name="User"
    )
    return models.Participant.objects.create(user=user, school="Test School")


@pytest.fixture
def application(participant, grade):
    return models.GradeApplication.objects.create(participant=participant, grade=grade)


@pytest.fixture
def application_grade2(participant, grade2):
    return models.GradeApplication.objects.create(
        participant=participant, grade=grade2
    )


# Stickers based on default resolvers
@pytest.fixture
def sticker_100():
    # Typically nr=1 or similar is "100% of points"
    return models.Sticker.objects.create(
        title="100 % bodů", nr=1, handpicked=False, assignment_limit="unlimited"
    )


@pytest.fixture
def sticker_limit_grade():
    return models.Sticker.objects.create(
        title="Limit Grade", nr=2, handpicked=False, assignment_limit="once_per_grade"
    )


@pytest.fixture
def sticker_limit_life():
    return models.Sticker.objects.create(
        title="Limit Life", nr=3, handpicked=False, assignment_limit="once_in_lifetime"
    )


@pytest.fixture
def mock_eligibility(monkeypatch):
    """Mocks the engine so we can explicitly dictate what stickers a participant earns."""
    def _apply_mock(eligibility_dict):
        def _mock_get_eligibility(series):
            return [(app, nrs) for app, nrs in eligibility_dict.items()]
        monkeypatch.setattr(
            "ksicht.core.stickers.services.get_eligibility", _mock_get_eligibility
        )

    return _apply_mock


def test_grant_stickers_basic(
    series1, application, sticker_100, mock_eligibility
):
    # Setup mock to say participant earns sticker_100
    mock_eligibility({application: [sticker_100.nr]})

    grant_stickers_for_series(series1)

    assignments = models.StickerAssignment.objects.filter(
        participant=application.participant
    )
    assert assignments.count() == 1
    a = assignments.first()
    assert a.sticker == sticker_100
    assert a.awarded_in_series == series1
    assert not a.assigned_after_publication


def test_grant_stickers_limit_once_per_grade(
    series1, series2, application, sticker_limit_grade, mock_eligibility
):
    # 1. Earn in series 1
    mock_eligibility({application: [sticker_limit_grade.nr]})
    grant_stickers_for_series(series1)
    assert models.StickerAssignment.objects.count() == 1


def test_grant_stickers_limit_once_in_lifetime(
    series1,
    series1_grade2,
    application,
    application_grade2,
    sticker_limit_life,
    mock_eligibility,
):
    # 1. Earn in grade 1
    mock_eligibility({application: [sticker_limit_life.nr]})
    grant_stickers_for_series(series1)
    assert models.StickerAssignment.objects.count() == 1

    # 2. Try to earn again in grade 2
    mock_eligibility({application_grade2: [sticker_limit_life.nr]})
    grant_stickers_for_series(series1_grade2)

    # Should still only be 1 assignment globally
    assert models.StickerAssignment.objects.count() == 1


def test_grant_stickers_removes_invalid_before_publication(
    series1, application, sticker_100, mock_eligibility
):
    # 1. Earn sticker
    mock_eligibility({application: [sticker_100.nr]})
    grant_stickers_for_series(series1)
    assert models.StickerAssignment.objects.count() == 1

    # 2. Score changes, no longer eligible, results not published yet
    series1.results_published = False
    series1.save()

    mock_eligibility({application: []})
    grant_stickers_for_series(series1)

    # Assignment should be deleted
    assert models.StickerAssignment.objects.count() == 0


def test_grant_stickers_keeps_invalid_after_publication(
    series1, application, sticker_100, mock_eligibility
):
    # 1. Earn sticker
    mock_eligibility({application: [sticker_100.nr]})
    grant_stickers_for_series(series1)
    assert models.StickerAssignment.objects.count() == 1

    # 2. Publish results
    series1.results_published = True
    series1.save()

    # 3. Score changes, no longer eligible
    mock_eligibility({application: []})
    grant_stickers_for_series(series1)

    # Assignment should NOT be deleted because results are published
    assert models.StickerAssignment.objects.count() == 1


def test_grant_stickers_adds_new_but_keeps_old_after_publication(
    series1, application, sticker_100, sticker_limit_grade, mock_eligibility
):
    # 1. Earn sticker 100 before publication
    mock_eligibility({application: [sticker_100.nr]})
    grant_stickers_for_series(series1)
    
    # 2. Publish results
    series1.results_published = True
    series1.save()
    
    # 3. Score changes: lose eligibility for 100, but gain eligibility for the new sticker
    mock_eligibility({application: [sticker_limit_grade.nr]})
    grant_stickers_for_series(series1)
    
    # Both stickers should exist. Old one is kept (because published), new one is added.
    assert models.StickerAssignment.objects.count() == 2
    assignments = models.StickerAssignment.objects.filter(participant=application.participant)
    stickers_assigned = set(a.sticker for a in assignments)
    assert sticker_100 in stickers_assigned
    assert sticker_limit_grade in stickers_assigned


def test_assigned_after_publication_flag(
    series1, application, sticker_100, mock_eligibility
):
    series1.results_published = True
    series1.save()

    # Earn sticker AFTER results are published
    mock_eligibility({application: [sticker_100.nr]})
    grant_stickers_for_series(series1)

    assignment = models.StickerAssignment.objects.first()
    assert assignment.assigned_after_publication is True


def test_historical_skip_limits(
    series1, series2, application, sticker_limit_grade, mock_eligibility
):
    """In backfill mode (skip_limits=True), assignment limits are completely ignored."""
    series1.results_published = True
    series1.save()

    # Earn in series 1
    mock_eligibility({application: [sticker_limit_grade.nr]})
    grant_stickers_for_series(series1, skip_limits=True)

    series2.results_published = True
    series2.save()

    # Earn in series 2 (limit would normally block this)
    mock_eligibility({application: [sticker_limit_grade.nr]})
    grant_stickers_for_series(series2, skip_limits=True)

    # Since it's backfill, both assignments should be created
    assert models.StickerAssignment.objects.count() == 2

    assignments = list(models.StickerAssignment.objects.all())
    for a in assignments:
        # Crucially, in backfill mode even if results correlate, the flag should be False
        assert a.assigned_after_publication is False

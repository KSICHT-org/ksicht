import csv
from datetime import date
from io import StringIO

import pytest

from django.core.exceptions import ValidationError

from ksicht.core import models
from ksicht.core.views.events import EventAttendeesExportView
from ksicht.forms import KsichtEditProfileForm


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+420777 123123", "+420 777 123 123"),
        ("+421 777123 123", "+421 777 123 123"),
        ("777123123", "+420 777 123 123"),
        ("+420 777 123 123", "+420 777 123 123"),
        ("+420", None),
        ("+44 1234567890", "+44 1234567890"),
    ],
)
def test_profile_phone_cleaning(raw, expected):
    form = KsichtEditProfileForm()
    form.cleaned_data = {"phone": raw}
    assert form.clean_phone() == expected


def test_phone_normalization_does_not_hide_invalid_input():
    form = KsichtEditProfileForm()
    form.cleaned_data = {"phone": "+420abc777123123"}
    with pytest.raises(ValidationError):
        form.clean_phone()


@pytest.mark.django_db
def test_export_headers_and_historical_phone_numbers():
    event = models.Event.objects.create(
        title="Test event", start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 2), capacity=10,
    )
    user = models.User.objects.create(email="test@example.invalid")
    models.EventAttendee.objects.create(
        user=user, event=event, user_phone="+421777 123123",
    )
    response = EventAttendeesExportView().render_to_response({"object": event})
    rows = list(csv.reader(StringIO(response.content.decode("utf-8"))))
    assert rows[0][6:] == ["Telefon", "Datum narození", "Škola", "Město"]
    assert rows[1][6] == "+421 777 123 123"

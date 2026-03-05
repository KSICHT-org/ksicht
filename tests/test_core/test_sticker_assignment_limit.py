"""Tests for the sticker assignment limit (graying-out) logic."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from ksicht.core import models


class TestStickerAssignmentLimit:
    """Tests for the Sticker.assignment_limit field itself."""

    def test_default_is_unlimited(self):
        sticker = models.Sticker(title="Test", nr=999, handpicked=False)
        assert sticker.assignment_limit == "unlimited"

    def test_assignment_limit_choices(self):
        choices = models.Sticker.AssignmentLimit.choices
        assert ("unlimited", "Neomezeně") in choices
        assert ("once_per_grade", "Jednou za ročník") in choices
        assert ("once_in_lifetime", "Jednou za život") in choices

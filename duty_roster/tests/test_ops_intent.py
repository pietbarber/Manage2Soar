from datetime import date

import pytest

from duty_roster.models import OpsIntent


@pytest.mark.django_db
def test_available_as_labels_returns_human_labels(db, django_user_model):
    # create a member
    user = django_user_model.objects.create(username="opsuser", email="ops@example.com")
    # create an OpsIntent with two valid activities
    day = date(2025, 11, 8)
    intent = OpsIntent.objects.create(
        member=user, date=day, available_as=["club", "towpilot"]
    )

    labels = intent.available_as_labels()
    assert isinstance(labels, list)
    assert "Club glider" in labels
    assert "Tow Pilot" in labels


@pytest.mark.django_db
def test_instruction_no_longer_in_available_activities():
    """'Instruction' was removed from AVAILABLE_ACTIVITIES (Issue #679) as ambiguous."""
    keys = [key for key, _label in OpsIntent.AVAILABLE_ACTIVITIES]
    assert "instruction" not in keys


@pytest.mark.django_db
def test_available_as_labels_falls_back_for_legacy_instruction_data(
    db, django_user_model
):
    """Old records that still have 'instruction' in available_as should fall back
    gracefully to the raw key rather than raising an error."""
    user = django_user_model.objects.create(
        username="legacy_user", email="legacy@example.com"
    )
    intent = OpsIntent.objects.create(
        member=user, date=date(2025, 11, 8), available_as=["instruction", "club"]
    )
    labels = intent.available_as_labels()
    # Falls back to raw key for missing entry; "Club glider" is still mapped.
    assert "instruction" in labels
    assert "Club glider" in labels

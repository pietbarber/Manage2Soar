from datetime import date

import pytest

from duty_roster.models import OpsIntent


@pytest.mark.django_db
def test_available_as_labels_returns_human_labels(db, django_user_model):
    # create a member
    user = django_user_model.objects.create(username="opsuser", email="ops@example.com")
    # create an OpsIntent with two activities
    day = date(2025, 11, 8)
    intent = OpsIntent.objects.create(
        member=user, date=day, available_as=["instruction", "club"]
    )

    labels = intent.available_as_labels()
    assert isinstance(labels, list)
    assert "Instruction" in labels
    assert "Club glider" in labels

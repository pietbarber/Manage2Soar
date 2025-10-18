import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from logsheet.models import (
    Airfield,
    Logsheet,
    LogsheetCloseout,
    Towplane,
    TowplaneCloseout,
)
from members.models import Member


@pytest.mark.django_db
def test_delete_button_not_shown_for_finalized_logsheet(client, active_member):
    airfield = Airfield.objects.create(name="Test Field")
    logsheet = Logsheet.objects.create(
        log_date="2024-01-01",
        airfield=airfield,
        created_by=active_member,
        finalized=True,
    )
    url = reverse("logsheet:index")
    client.force_login(active_member)
    response = client.get(url)
    assert response.status_code == 200
    # The delete button should not be present for finalized logsheets
    assert (
        f"action=\"{reverse('logsheet:delete', args=[logsheet.pk])}\""
        not in response.content.decode()
    )


@pytest.mark.django_db
def test_delete_button_not_shown_for_logsheet_with_towplane_closeout(
    client, active_member
):
    airfield = Airfield.objects.create(name="Test Field")
    towplane = Towplane.objects.create(n_number="N12345")
    logsheet = Logsheet.objects.create(
        log_date="2024-01-02",
        airfield=airfield,
        created_by=active_member,
        finalized=False,
    )
    TowplaneCloseout.objects.create(
        logsheet=logsheet,
        towplane=towplane,
        start_tach=100,
        end_tach=110,
        tach_time=10,
        fuel_added=20,
    )
    url = reverse("logsheet:index")
    client.force_login(active_member)
    response = client.get(url)
    assert response.status_code == 200
    # The delete button should not be present for logsheets with towplane closeouts
    assert (
        f"action=\"{reverse('logsheet:delete', args=[logsheet.pk])}\""
        not in response.content.decode()
    )

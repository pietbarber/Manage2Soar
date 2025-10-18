import pytest
from django.urls import reverse

from logsheet.models import Logsheet


@pytest.mark.django_db
def test_delete_empty_logsheet(client, active_member, airfield):
    # Create an empty logsheet (no flights, closeout, or payments)
    logsheet = Logsheet.objects.create(
        log_date="2024-01-01", airfield=airfield, created_by=active_member
    )
    url = reverse("logsheet:delete", args=[logsheet.pk])
    # active_member is a User, not Member, so use directly
    client.force_login(active_member)
    response = client.post(url, follow=True)
    assert response.status_code == 200
    assert not Logsheet.objects.filter(pk=logsheet.pk).exists()


@pytest.mark.django_db
def test_delete_nonempty_logsheet_forbidden(client, active_member, airfield, glider):
    # Create a logsheet with a flight (not empty)
    logsheet = Logsheet.objects.create(
        log_date="2024-01-01", airfield=airfield, created_by=active_member
    )
    logsheet.flights.create(glider=glider, pilot=active_member, launch_method="tow")
    url = reverse("logsheet:delete", args=[logsheet.pk])
    client.force_login(active_member)
    response = client.post(url)
    assert response.status_code == 403
    assert Logsheet.objects.filter(pk=logsheet.pk).exists()

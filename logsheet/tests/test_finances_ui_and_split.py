import pytest
from django.urls import reverse

from logsheet.models import Flight

# Fixtures are provided by conftest.py and fixtures_finances.py


@pytest.mark.django_db
def test_member_charges_table_no_splits_column(
    client, active_member, logsheet_with_flights
):
    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)
    assert response.status_code == 200
    assert b"<th>Splits</th>" not in response.content
    assert b"Member Charges" in response.content


@pytest.mark.django_db
def test_payment_method_tracker_has_splits_column(
    client, active_member, logsheet_with_flights
):
    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)
    assert response.status_code == 200
    assert b"Edit Split" in response.content
    assert b"Payment Method Tracker" in response.content


@pytest.mark.django_db
def test_summary_by_flight_table_layout(client, active_member, logsheet_with_flights):
    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)
    assert response.status_code == 200
    assert b"Summary by Flight" in response.content
    content = response.content.decode("utf-8")
    # Check that the expected column headers are present in the Summary by Flight table
    assert ">Pilot</th>" in content
    assert ">Glider</th>" in content
    assert ">Duration</th>" in content
    assert ">Tow Cost</th>" in content
    assert ">Rental Cost</th>" in content
    assert ">Total</th>" in content
    assert ">Split</th>" in content
    # Check that the table footer has proper structure
    assert 'colspan="3"' in content
    assert "Totals:" in content


@pytest.mark.django_db
def test_update_flight_split_ajax(
    client, active_member, logsheet_with_flights, another_member
):
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    assert flight is not None, "Test setup failed: no Flight created."
    assert another_member is not None, "Test setup failed: another_member missing."
    url = reverse("logsheet:update_flight_split", args=[flight.pk])
    client.force_login(active_member)
    data = {
        "flight_id": flight.pk,
        "split_with": another_member.pk,
        "split_type": "even",
    }
    response = client.post(url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 200
    assert response.json().get("success")
    flight.refresh_from_db()
    assert flight.split_with == another_member
    assert flight.split_type == "even"


@pytest.mark.django_db
def test_update_flight_split_ajax_invalid(client, active_member, logsheet_with_flights):
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    assert flight is not None, "Test setup failed: no Flight created."
    url = reverse("logsheet:update_flight_split", args=[flight.pk])
    client.force_login(active_member)
    # Invalid split_type should be rejected
    data = {"flight_id": flight.pk, "split_with": "", "split_type": "invalid_type"}
    response = client.post(url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 400
    assert not response.json().get("success")
    assert "error" in response.json()


@pytest.mark.django_db
def test_clear_flight_split_ajax(client, active_member, logsheet_with_flights):
    """Clearing the split via AJAX should succeed and remove split_with and split_type."""
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    assert flight is not None, "Test setup failed: no Flight created."
    url = reverse("logsheet:update_flight_split", args=[flight.pk])
    client.force_login(active_member)
    # Send empty values to clear
    data = {"flight_id": flight.pk, "split_with": "", "split_type": ""}
    response = client.post(url, data, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 200
    assert response.json().get("success")
    flight.refresh_from_db()
    assert flight.split_with is None
    assert flight.split_type is None

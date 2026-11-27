import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from logsheet.admin import FlightAdminForm
from logsheet.models import Flight


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="flight-admin-superuser", password="password"
    )


@pytest.fixture
def flight(logsheet, active_member, glider, airfield):
    return Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        airfield=airfield,
        flight_type="dual",
    )


@pytest.mark.django_db
def test_flight_admin_form_excludes_flight_type(flight):
    """The admin form keeps every Flight field except the legacy flight_type."""
    form = FlightAdminForm(instance=flight)

    assert "flight_type" not in form.fields
    assert "landing_time" in form.fields


@pytest.mark.django_db
def test_flight_add_form_omits_flight_type(client, superuser):
    """The admin add form no longer shows the Flight Type field (Issue #1163)."""
    client.force_login(superuser)

    response = client.get(reverse("admin:logsheet_flight_add"))

    assert response.status_code == 200
    assert "flight_type" not in response.context["adminform"].form.fields


@pytest.mark.django_db
def test_flight_change_form_saves_without_flight_type(client, superuser, flight):
    """Editing a flight in the admin saves without a Flight Type error (Issue #1163).

    The previously stored flight_type value is preserved because the form
    no longer contains the field.
    """
    client.force_login(superuser)

    # Model booleans without blank=True are required checkboxes in the
    # ModelForm, so the flags must be submitted explicitly.
    response = client.post(
        reverse("admin:logsheet_flight_change", args=[flight.pk]),
        {
            "logsheet": flight.logsheet_id,
            "pilot": flight.pilot_id,
            "glider": flight.glider_id,
            "airfield": flight.airfield_id,
            "launch_method": "tow",
            "commercial_ride": "on",
            "is_retrieve": "on",
            "free_tow": "on",
            "free_rental": "on",
            "launch_time": "10:00:00",
            "landing_time": "11:30:00",
        },
    )

    assert response.status_code == 302
    flight.refresh_from_db()
    assert flight.landing_time.strftime("%H:%M") == "11:30"
    assert flight.flight_type == "dual"

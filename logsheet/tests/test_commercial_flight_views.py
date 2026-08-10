from datetime import date, time

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from logsheet.models import CommercialRide, CommercialTicket, Flight
from siteconfig.models import SiteConfiguration


@pytest.mark.django_db
def test_add_commercial_flight_redeems_ticket_and_creates_ride(
    client, active_member, glider, airfield
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    active_member.glider_rating = "commercial"
    active_member.save(update_fields=["glider_rating"])

    ticket = CommercialTicket.objects.create(ticket_number="T-500")

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])
    response = client.post(
        url,
        data={
            "pilot": active_member.pk,
            "glider": glider.pk,
            "launch_time": "09:00",
            "landing_time": "09:25",
            "commercial_ride": "on",
            "ticket_number": ticket.ticket_number,
            "passenger_name": "",
            "release_altitude": "3000",
        },
    )

    assert response.status_code == 302

    flight = Flight.objects.get(logsheet=logsheet)
    ticket.refresh_from_db(from_queryset=None)

    assert flight.commercial_ride is True
    assert flight.passenger is None
    assert flight.passenger_name == ""
    assert ticket.status == CommercialTicket.Status.REDEEMED
    assert ticket.flight == flight
    assert CommercialRide.objects.filter(flight=flight, ticket=ticket).exists()


@pytest.mark.django_db
def test_add_commercial_flight_requires_enabled_feature(
    client, active_member, glider, airfield
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=False,
    )

    active_member.glider_rating = "commercial"
    active_member.save(update_fields=["glider_rating"])

    CommercialTicket.objects.create(ticket_number="T-501")

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])
    response = client.post(
        url,
        data={
            "pilot": active_member.pk,
            "glider": glider.pk,
            "launch_time": "09:00",
            "commercial_ride": "on",
            "ticket_number": "T-501",
            "release_altitude": "3000",
        },
    )

    assert response.status_code == 200
    assert not Flight.objects.filter(logsheet=logsheet).exists()
    assert "commercial_ride" in response.context["form"].errors


@pytest.mark.django_db
def test_add_commercial_flight_rolls_back_when_ticket_link_fails(
    client, active_member, glider, airfield, monkeypatch
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    active_member.glider_rating = "commercial"
    active_member.save(update_fields=["glider_rating"])

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    def _raise_link_error(*, flight, ticket_number):
        raise ValidationError("Ticket is already redeemed by a different flight.")

    monkeypatch.setattr(
        "logsheet.views._link_commercial_ticket_to_flight", _raise_link_error
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])
    response = client.post(
        url,
        data={
            "pilot": active_member.pk,
            "glider": glider.pk,
            "launch_time": "09:00",
            "landing_time": "09:25",
            "commercial_ride": "on",
            "ticket_number": "T-DOES-NOT-MATTER",
            "passenger_name": "",
            "release_altitude": "3000",
        },
    )

    assert response.status_code == 200
    assert "ticket_number" in response.context["form"].errors
    assert not Flight.objects.filter(logsheet=logsheet).exists()


@pytest.mark.django_db
def test_edit_commercial_flight_rolls_back_when_ticket_link_fails(
    client, active_member, glider, airfield, monkeypatch
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    active_member.glider_rating = "commercial"
    active_member.save(update_fields=["glider_rating"])

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        launch_time=time(8, 30),
        landing_time=time(8, 55),
        passenger_name="Keep Me",
        commercial_ride=False,
    )

    def _raise_link_error(*, flight, ticket_number):
        raise ValidationError("Ticket is already redeemed by a different flight.")

    monkeypatch.setattr(
        "logsheet.views._link_commercial_ticket_to_flight", _raise_link_error
    )

    client.force_login(active_member)
    url = reverse("logsheet:edit_flight", args=[logsheet.pk, flight.pk])
    response = client.post(
        url,
        data={
            "pilot": active_member.pk,
            "glider": glider.pk,
            "launch_time": "09:00",
            "landing_time": "09:25",
            "commercial_ride": "on",
            "ticket_number": "T-DOES-NOT-MATTER",
            "passenger_name": "",
            "release_altitude": "3000",
        },
    )

    assert response.status_code == 200
    assert "ticket_number" in response.context["form"].errors
    flight.refresh_from_db(from_queryset=None)
    assert flight.commercial_ride is False
    assert flight.passenger_name == "Keep Me"


@pytest.mark.django_db
def test_add_pending_commercial_flight_soft_locks_ticket_without_redeeming(
    client, active_member, glider, airfield
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    active_member.glider_rating = "commercial"
    active_member.save(update_fields=["glider_rating"])

    ticket = CommercialTicket.objects.create(ticket_number="T-700")

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])
    response = client.post(
        url,
        data={
            "pilot": active_member.pk,
            "glider": glider.pk,
            "commercial_ride": "on",
            "ticket_number": ticket.ticket_number,
            "passenger_name": "",
            "release_altitude": "3000",
        },
    )

    assert response.status_code == 302

    flight = Flight.objects.get(logsheet=logsheet)
    ticket.refresh_from_db(from_queryset=None)

    assert flight.launch_time is None
    assert ticket.status == CommercialTicket.Status.AVAILABLE
    assert ticket.flight == flight
    assert CommercialRide.objects.filter(flight=flight, ticket=ticket).exists()


@pytest.mark.django_db
def test_launch_now_redeems_soft_locked_ticket(client, active_member, glider, airfield):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    active_member.glider_rating = "commercial"
    active_member.save(update_fields=["glider_rating"])

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )
    ticket = CommercialTicket.objects.create(ticket_number="T-701")
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        commercial_ride=True,
        release_altitude=3000,
    )
    CommercialRide.objects.create(
        flight=flight,
        ticket=ticket,
        commercial_pilot=active_member,
        revenue_amount=ticket.amount_paid,
    )

    ticket.refresh_from_db(from_queryset=None)
    assert ticket.status == CommercialTicket.Status.AVAILABLE

    client.force_login(active_member)
    url = reverse("logsheet:launch_flight_now", args=[flight.pk])
    response = client.post(
        url,
        data='{"launch_time":"10:30"}',
        content_type="application/json",
    )

    assert response.status_code == 200
    ticket.refresh_from_db(from_queryset=None)
    assert ticket.status == CommercialTicket.Status.REDEEMED
    assert ticket.flight == flight


@pytest.mark.django_db
def test_add_flight_copies_logsheet_airfield_when_missing(
    client, active_member, glider
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    from logsheet.models import Airfield, Logsheet

    logsheet_airfield = Airfield.objects.create(
        name="Skyline",
        identifier="KSKY",
    )
    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=logsheet_airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])
    response = client.post(
        url,
        data={
            "pilot": active_member.pk,
            "glider": glider.pk,
            "launch_time": "09:00",
            "landing_time": "09:25",
            "release_altitude": "3000",
        },
    )

    assert response.status_code == 302
    flight = Flight.objects.get(logsheet=logsheet)
    assert flight.airfield == logsheet_airfield


@pytest.mark.django_db
def test_edit_flight_copies_logsheet_airfield_when_missing(
    client, active_member, glider
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    from logsheet.models import Airfield, Logsheet

    logsheet_airfield = Airfield.objects.create(
        name="Front Royal",
        identifier="KFRR",
    )
    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=logsheet_airfield,
        created_by=active_member,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        airfield=None,
        launch_time=time(8, 30),
        landing_time=time(8, 55),
    )

    client.force_login(active_member)
    url = reverse("logsheet:edit_flight", args=[logsheet.pk, flight.pk])
    response = client.post(
        url,
        data={
            "pilot": active_member.pk,
            "glider": glider.pk,
            "launch_time": "09:00",
            "landing_time": "09:25",
            "release_altitude": "3000",
        },
    )

    assert response.status_code == 302
    flight.refresh_from_db(from_queryset=None)
    assert flight.airfield == logsheet_airfield


@pytest.mark.django_db
def test_add_flight_ajax_returns_setup_error_when_site_configuration_missing(
    client, active_member, airfield
):
    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:add_flight", args=[logsheet.pk]),
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error_code"] == "flight_form_setup_incomplete"
    assert "Site Configuration is missing" in payload["error"]


@pytest.mark.django_db
def test_edit_flight_ajax_returns_setup_error_when_site_configuration_missing(
    client, active_member, glider, airfield
):
    from logsheet.models import Flight, Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
    )

    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:edit_flight", args=[logsheet.pk, flight.pk]),
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error_code"] == "flight_form_setup_incomplete"
    assert "Site Configuration is missing" in payload["error"]


@pytest.mark.django_db
def test_launch_now_rolls_back_launch_time_when_ticket_link_fails(
    client, active_member, glider, airfield, monkeypatch
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    active_member.glider_rating = "commercial"
    active_member.save(update_fields=["glider_rating"])

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )
    ticket = CommercialTicket.objects.create(ticket_number="T-702")
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        commercial_ride=True,
        release_altitude=3000,
    )
    CommercialRide.objects.create(
        flight=flight,
        ticket=ticket,
        commercial_pilot=active_member,
        revenue_amount=ticket.amount_paid,
    )

    def _raise_link_error(*, flight, ticket_number):
        raise ValidationError("Ticket is already redeemed by a different flight.")

    monkeypatch.setattr(
        "logsheet.views._link_commercial_ticket_to_flight", _raise_link_error
    )

    client.force_login(active_member)
    url = reverse("logsheet:launch_flight_now", args=[flight.pk])
    response = client.post(
        url,
        data='{"launch_time":"10:45"}',
        content_type="application/json",
    )

    assert response.status_code == 400
    flight.refresh_from_db(from_queryset=None)
    ticket.refresh_from_db(from_queryset=None)
    assert flight.launch_time is None
    assert ticket.status == CommercialTicket.Status.AVAILABLE


@pytest.mark.django_db
def test_add_flight_ajax_returns_unexpected_error_code_on_generic_exception(
    client, active_member, airfield, monkeypatch
):
    """Unexpected exceptions during FlightForm init return error_code='flight_form_unexpected_error'."""
    from logsheet.models import Logsheet

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
    )
    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated unexpected form init failure")

    monkeypatch.setattr("logsheet.views.FlightForm", _boom)

    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:add_flight", args=[logsheet.pk]),
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error_code"] == "flight_form_unexpected_error"
    assert "unexpected server error" in payload["error"]


@pytest.mark.django_db
def test_edit_flight_ajax_returns_unexpected_error_code_on_generic_exception(
    client, active_member, glider, airfield, monkeypatch
):
    """Unexpected exceptions during FlightForm init return error_code='flight_form_unexpected_error'."""
    from logsheet.models import Flight, Logsheet

    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
    )
    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )
    flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated unexpected form init failure")

    monkeypatch.setattr("logsheet.views.FlightForm", _boom)

    client.force_login(active_member)
    response = client.get(
        reverse("logsheet:edit_flight", args=[logsheet.pk, flight.pk]),
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 500
    payload = response.json()
    assert payload["error_code"] == "flight_form_unexpected_error"
    assert "unexpected server error" in payload["error"]


def _flight_post_payload(
    active_member,
    glider,
    *,
    client_token=None,
    launch_time="09:00",
    landing_time="09:25",
):
    payload = {
        "pilot": active_member.pk,
        "glider": glider.pk,
        "launch_time": launch_time,
        "landing_time": landing_time,
        "release_altitude": "3000",
    }
    if client_token is not None:
        payload["client_token"] = client_token
    return payload


@pytest.mark.django_db
def test_add_flight_same_client_token_twice_creates_single_flight(
    client, active_member, glider, airfield
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])

    response1 = client.post(
        url,
        data=_flight_post_payload(active_member, glider, client_token="token-001"),
    )
    response2 = client.post(
        url,
        data=_flight_post_payload(active_member, glider, client_token="token-001"),
    )

    assert response1.status_code == 302
    assert response2.status_code == 302
    assert Flight.objects.filter(logsheet=logsheet).count() == 1


@pytest.mark.django_db
def test_add_flight_without_client_token_creates_multiple_flights(
    client, active_member, glider, airfield
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])

    response1 = client.post(url, data=_flight_post_payload(active_member, glider))
    response2 = client.post(
        url,
        data=_flight_post_payload(
            active_member,
            glider,
            launch_time="10:00",
            landing_time="10:25",
        ),
    )

    assert response1.status_code == 302
    assert response2.status_code == 302
    assert Flight.objects.filter(logsheet=logsheet).count() == 2


@pytest.mark.django_db
def test_add_flight_different_client_tokens_create_distinct_flights(
    client, active_member, glider, airfield
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    url = reverse("logsheet:add_flight", args=[logsheet.pk])

    response1 = client.post(
        url,
        data=_flight_post_payload(active_member, glider, client_token="token-101"),
    )
    response2 = client.post(
        url,
        data=_flight_post_payload(
            active_member,
            glider,
            client_token="token-102",
            launch_time="10:00",
            landing_time="10:25",
        ),
    )

    assert response1.status_code == 302
    assert response2.status_code == 302
    assert Flight.objects.filter(logsheet=logsheet).count() == 2


@pytest.mark.django_db
def test_add_flight_integrityerror_fallback_returns_success_and_single_row(
    client, active_member, glider, airfield, monkeypatch
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    token = "race-token-001"
    existing = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        launch_time=time(8, 0),
        landing_time=time(8, 25),
        release_altitude=3000,
        client_token=token,
    )

    # Simulate race timing: pre-save lookup misses, post-IntegrityError lookup finds row.
    lookup_calls = {"count": 0}

    def _mock_lookup(current_logsheet, current_token):
        assert current_logsheet == logsheet
        assert current_token == token
        lookup_calls["count"] += 1
        if lookup_calls["count"] == 1:
            return None
        return existing

    monkeypatch.setattr(
        "logsheet.views._find_existing_flight_by_client_token", _mock_lookup
    )

    original_save = Flight.save

    def _raise_integrity_for_new(*args, **kwargs):
        self = args[0]
        if self.pk is None and self.client_token == token:
            raise IntegrityError("duplicate key value violates unique constraint")
        return original_save(*args, **kwargs)

    monkeypatch.setattr(Flight, "save", _raise_integrity_for_new)

    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_flight", args=[logsheet.pk]),
        data=_flight_post_payload(active_member, glider, client_token=token),
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert Flight.objects.filter(logsheet=logsheet, client_token=token).count() == 1


@pytest.mark.django_db
def test_add_flight_overlong_client_token_returns_validation_error(
    client, active_member, glider, airfield
):
    SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="example.org",
        club_abbreviation="TC",
        commercial_rides_enabled=True,
    )

    from logsheet.models import Logsheet

    logsheet = Logsheet.objects.create(
        log_date=date.today(),
        airfield=airfield,
        created_by=active_member,
    )

    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:add_flight", args=[logsheet.pk]),
        data=_flight_post_payload(active_member, glider, client_token="x" * 65),
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
    )

    assert response.status_code == 400
    assert "Invalid submission token" in response.content.decode()
    assert Flight.objects.filter(logsheet=logsheet).count() == 0

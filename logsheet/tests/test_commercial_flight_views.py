from datetime import date, time

import pytest
from django.core.exceptions import ValidationError
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
    ticket.refresh_from_db()

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
    flight.refresh_from_db()
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
    ticket.refresh_from_db()

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

    ticket.refresh_from_db()
    assert ticket.status == CommercialTicket.Status.AVAILABLE

    client.force_login(active_member)
    url = reverse("logsheet:launch_flight_now", args=[flight.pk])
    response = client.post(
        url,
        data='{"launch_time":"10:30"}',
        content_type="application/json",
    )

    assert response.status_code == 200
    ticket.refresh_from_db()
    assert ticket.status == CommercialTicket.Status.REDEEMED
    assert ticket.flight == flight

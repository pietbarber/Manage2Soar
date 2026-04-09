from datetime import date

import pytest
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

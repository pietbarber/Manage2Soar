from datetime import time
from decimal import Decimal

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
def test_finances_uses_computed_duration_when_duration_is_null(
    client, active_member, logsheet_with_flights, another_member
):
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    assert flight is not None, "Test setup failed: no Flight created."

    # Render the finalized View Split modal path where data-duration is used.
    flight.split_with = another_member
    flight.split_type = "even"
    flight.save(update_fields=["split_with", "split_type"])
    logsheet_with_flights.finalized = True
    logsheet_with_flights.save(update_fields=["finalized"])

    # Simulate legacy/backfill gap where stored DurationField is null.
    Flight.objects.filter(pk=flight.pk).update(duration=None)
    flight.refresh_from_db()
    assert flight.duration is None
    assert flight.computed_duration is not None

    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "<td>None</td>" not in content
    assert str(flight.computed_duration) in content
    assert f'data-duration="{flight.computed_duration}"' in content
    assert 'data-duration="None"' not in content


@pytest.mark.django_db
def test_finances_preserves_zero_computed_duration(
    client, active_member, logsheet_with_flights
):
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    assert flight is not None, "Test setup failed: no Flight created."

    # A true zero-duration flight should render as 0:00:00, not the fallback em-dash.
    Flight.objects.filter(pk=flight.pk).update(
        duration=None,
        launch_time=time(10, 0),
        landing_time=time(10, 0),
    )
    flight.refresh_from_db()
    assert str(flight.computed_duration) == "0:00:00"

    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "0:00:00" in content


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


@pytest.mark.django_db
def test_misc_charges_integration(client, active_member, logsheet_with_flights):
    """
    Test that miscellaneous charges are correctly displayed in finance view.

    Issue #66: Aerotow retrieve fees
    Issue #413: Miscellaneous charges

    This test verifies:
    1. MemberCharge linked to logsheet appears in Miscellaneous Charges section
    2. Charge is included in member's total in Member Charges table
    3. Misc column is conditionally displayed when misc charges exist
    """
    from logsheet.models import MemberCharge
    from members.models import Member
    from siteconfig.models import ChargeableItem

    # Create a chargeable item
    item = ChargeableItem.objects.create(
        name="T-Shirt",
        price=Decimal("25.00"),
        unit=ChargeableItem.UnitType.EACH,
        is_active=True,
    )

    # Get a member who has flights (to verify charge is added to their total)
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    member = flight.pilot if (flight and flight.pilot) else active_member

    # Create a member charge linked to the logsheet
    MemberCharge.objects.create(
        member=member,
        chargeable_item=item,
        quantity=Decimal("2.00"),
        date=logsheet_with_flights.log_date,
        logsheet=logsheet_with_flights,
        notes="Test merchandise purchase",
        entered_by=active_member,
    )

    # Load the finance management page
    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200

    # Verify misc charge appears in Miscellaneous Charges section
    assert "Miscellaneous Charges" in response.content.decode("utf-8")
    assert "T-Shirt" in response.content.decode("utf-8")
    assert "50.00" in response.content.decode("utf-8")  # 2 × $25.00
    assert "Test merchandise purchase" in response.content.decode("utf-8")

    # Verify Misc column is displayed in Member Charges table
    assert ">Misc</th>" in response.content.decode(
        "utf-8"
    ) or ">Misc<" in response.content.decode("utf-8")

    # Verify charge is included in member's row
    assert member.get_full_name() in response.content.decode("utf-8") or str(
        member
    ) in response.content.decode("utf-8")

    # Verify context data
    assert "misc_charges_data" in response.context
    assert "total_misc_charges" in response.context
    assert response.context["total_misc_charges"] == Decimal("50.00")


@pytest.mark.django_db
def test_misc_charges_column_not_shown_when_empty(
    client, active_member, logsheet_with_flights
):
    """Verify Misc column is NOT shown when there are no misc charges."""
    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200

    # Misc column should not appear when no charges exist
    # (The template should conditionally hide it)
    assert "total_misc_charges" in response.context
    assert response.context["total_misc_charges"] == Decimal("0.00")

    # Verify Misc column header is actually hidden from HTML
    assert ">Misc</th>" not in response.content.decode(
        "utf-8"
    ) and ">Misc<" not in response.content.decode("utf-8")


@pytest.mark.django_db
def test_finances_excludes_commercial_ride_from_member_charges(
    client, active_member, another_member, logsheet_with_flights
):
    from logsheet.models import CommercialRide, CommercialTicket
    from members.models import Member

    commercial_only_member = Member.objects.create_user(
        username="commercial_only_member",
        password="testpass123",
        first_name="Commercial",
        last_name="Only",
        membership_status="Full Member",
    )

    commercial_flight = Flight.objects.create(
        logsheet=logsheet_with_flights,
        pilot=commercial_only_member,
        glider=Flight.objects.filter(logsheet=logsheet_with_flights).first().glider,
        flight_type="intro",
        commercial_ride=True,
        launch_time=time(10, 0),
        landing_time=time(10, 30),
        tow_cost_actual=Decimal("200.00"),
        rental_cost_actual=Decimal("150.00"),
    )
    ticket = CommercialTicket.objects.create(ticket_number="T-300")
    ticket.transition_to(CommercialTicket.Status.REDEEMED, flight=commercial_flight)
    CommercialRide.objects.create(
        flight=commercial_flight,
        ticket=ticket,
        commercial_pilot=commercial_only_member,
        revenue_amount=Decimal("350.00"),
    )

    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200
    billed_members = {
        row["member"].id for row in response.context["member_payment_data_sorted"]
    }
    assert commercial_only_member.id not in billed_members


@pytest.mark.django_db
def test_export_finances_csv_excludes_commercial_ride_rows(
    client, active_member, another_member, logsheet, glider
):
    from logsheet.models import CommercialRide, CommercialTicket, Towplane

    towplane = Towplane.objects.create(name="Tow 1", n_number="N123AA", is_active=True)

    normal_flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=active_member,
        glider=glider,
        towplane=towplane,
        flight_type="dual",
        launch_time=time(9, 0),
        landing_time=time(9, 30),
        release_altitude=3000,
        tow_cost_actual=Decimal("50.00"),
        rental_cost_actual=Decimal("25.00"),
    )
    assert normal_flight is not None

    commercial_flight = Flight.objects.create(
        logsheet=logsheet,
        pilot=another_member,
        glider=glider,
        towplane=towplane,
        flight_type="intro",
        commercial_ride=True,
        launch_time=time(10, 0),
        landing_time=time(10, 30),
        release_altitude=6600,
        tow_cost_actual=Decimal("200.00"),
        rental_cost_actual=Decimal("150.00"),
    )
    ticket = CommercialTicket.objects.create(ticket_number="T-301")
    ticket.transition_to(CommercialTicket.Status.REDEEMED, flight=commercial_flight)
    CommercialRide.objects.create(
        flight=commercial_flight,
        ticket=ticket,
        commercial_pilot=another_member,
        revenue_amount=Decimal("350.00"),
    )

    logsheet.finalized = True
    logsheet.save(update_fields=["finalized"])

    url = reverse("logsheet:export_logsheet_finances_csv", args=[logsheet.pk])
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "3000Tow1Tow" in body
    assert "6600Tow1Tow" not in body

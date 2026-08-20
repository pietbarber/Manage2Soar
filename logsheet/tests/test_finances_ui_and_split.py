from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from billing.models import FlightChargeSnapshot, LedgerEntry
from billing.periods import close_period
from billing.services import post_flight_charges
from logsheet.models import Flight, FlightSplitRequest, LogsheetPayment
from logsheet.utils.flight_charges import get_billing_allocations
from siteconfig.models import (
    BillingPricingMode,
    MembershipBillingRule,
    MembershipStatus,
    SiteConfiguration,
)

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
def test_member_payment_defaults_to_on_account(
    client, active_member, logsheet_with_flights
):
    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)

    response = client.get(url)

    assert response.status_code == 200
    payment = LogsheetPayment.objects.get(
        logsheet=logsheet_with_flights,
        member=active_member,
    )
    assert payment.payment_method == "account"
    row = next(
        row
        for row in response.context["member_payment_data_sorted"]
        if row["member"].pk == active_member.pk
    )
    assert row["payment_method"] == "account"


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
def test_summary_by_flight_footer_includes_instruction_when_present(
    client, active_member, logsheet_with_flights
):
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    assert flight is not None

    flight.tow_cost_actual = Decimal("40.00")
    flight.rental_cost_actual = Decimal("20.00")
    flight.instruction_fee_actual = Decimal("12.00")
    flight.save(
        update_fields=[
            "tow_cost_actual",
            "rental_cost_actual",
            "instruction_fee_actual",
        ]
    )

    logsheet_with_flights.finalized = True
    logsheet_with_flights.save(update_fields=["finalized"])

    url = reverse("logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk])
    client.force_login(active_member)
    response = client.get(url)

    assert response.status_code == 200
    assert response.context["instruction_fees_present"] is True
    assert response.context["total_instruction"] == Decimal("12.00")
    assert response.context["total_sum"] == Decimal("72.00")

    content = response.content.decode("utf-8")
    assert ">Instruction Fee</th>" in content
    assert "$12.00" in content


@pytest.mark.django_db
def test_finalized_legacy_null_instruction_snapshot_stays_zero(
    client,
    active_member,
    another_member,
    member_instructor,
    logsheet_with_flights,
):
    MembershipStatus.objects.update_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    config = SiteConfiguration.objects.first() or SiteConfiguration.objects.create(
        club_name="Test Club",
        domain_name="test.example.com",
        club_abbreviation="TC",
    )
    config.billing_rules_enabled = True
    config.instructor_time_charges_enabled = True
    config.billing_pricing_mode = BillingPricingMode.MATRIX
    config.save(
        update_fields=[
            "billing_rules_enabled",
            "instructor_time_charges_enabled",
            "billing_pricing_mode",
        ]
    )

    full_status = MembershipStatus.objects.get(name="Full Member")
    MembershipBillingRule.objects.update_or_create(
        membership_status=full_status,
        defaults={
            "is_active": True,
            "charge_instruction_per_instructed_flight": True,
            "instruction_flat_fee_per_flight": Decimal("25.00"),
        },
    )

    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    assert flight is not None
    flight.instructor = member_instructor
    flight.tow_cost_actual = Decimal("30.00")
    flight.rental_cost_actual = Decimal("10.00")
    flight.instruction_fee_actual = None
    flight.split_with = another_member
    flight.split_type = "tow"
    flight.save(
        update_fields=[
            "instructor",
            "tow_cost_actual",
            "rental_cost_actual",
            "instruction_fee_actual",
            "split_with",
            "split_type",
        ]
    )

    logsheet_with_flights.finalized = True
    logsheet_with_flights.save(update_fields=["finalized"])

    finance_url = reverse(
        "logsheet:manage_logsheet_finances", args=[logsheet_with_flights.pk]
    )
    client.force_login(active_member)
    response = client.get(finance_url)

    assert response.status_code == 200
    assert response.context["total_instruction"] == Decimal("0.00")
    flight_row = next(
        row for row in response.context["flight_data"] if row[0].pk == flight.pk
    )
    assert flight_row[1]["instruction"] == Decimal("0.00")
    assert flight_row[1]["total"] == Decimal("40.00")

    content = response.content.decode("utf-8")
    assert 'data-instruction-cost="0.00"' in content

    export_url = reverse(
        "logsheet:export_logsheet_finances_csv", args=[logsheet_with_flights.pk]
    )
    export_response = client.get(export_url)
    assert export_response.status_code == 200
    export_content = export_response.content.decode("utf-8")
    assert "Instruction Fee" not in export_content


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
def test_finalized_split_request_corrects_only_after_partner_accepts(
    client, active_member, another_member, logsheet_with_flights
):
    config = SiteConfiguration.objects.first() or SiteConfiguration.objects.create(
        club_name="Split Correction Test Club",
        domain_name="split-correction.example.com",
        club_abbreviation="SCT",
    )
    config.billing_app_enabled = True
    config.save(update_fields=["billing_app_enabled"])
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    flight.tow_cost_actual = Decimal("20.00")
    flight.rental_cost_actual = Decimal("10.00")
    flight.save(update_fields=["tow_cost_actual", "rental_cost_actual"])
    logsheet_with_flights.finalized = True
    logsheet_with_flights.save(update_fields=["finalized"])
    active_member.treasurer = True
    active_member.save(update_fields=["treasurer"])

    post_flight_charges(
        flight=flight,
        actor=active_member,
        allocations=get_billing_allocations(flight),
    )
    initial_entry_count = LedgerEntry.objects.filter(flight=flight).count()

    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:update_flight_split", args=[flight.pk]),
        {
            "split_with": another_member.pk,
            "split_type": "rental",
            "reason": "Corrected payer allocation",
        },
    )

    assert response.status_code == 200
    assert response.json()["request_pending"] is True
    assert LedgerEntry.objects.filter(flight=flight).count() == initial_entry_count

    split_request = FlightSplitRequest.objects.get(flight=flight)
    assert split_request.status == FlightSplitRequest.Status.PENDING
    assert split_request.requested_member == another_member

    client.force_login(another_member)
    response = client.post(
        reverse("logsheet:flight_split_request_detail", args=[split_request.token]),
        {"decision": "accept"},
    )

    assert response.status_code == 302
    split_request.refresh_from_db()
    assert split_request.status == FlightSplitRequest.Status.ACCEPTED
    assert LedgerEntry.objects.filter(flight=flight).count() == initial_entry_count + 2
    assert LedgerEntry.objects.filter(kind=LedgerEntry.Kind.REVERSAL).count() == 2
    assert set(
        FlightChargeSnapshot.objects.filter(flight=flight).values_list(
            "allocation_version", flat=True
        )
    ) == {1, 2}


@pytest.mark.django_db
def test_finalized_split_request_rejects_self_as_partner(
    client, active_member, logsheet_with_flights
):
    config = SiteConfiguration.objects.first() or SiteConfiguration.objects.create(
        club_name="Split Correction Test Club",
        domain_name="split-correction.example.com",
        club_abbreviation="SCT",
    )
    config.billing_app_enabled = True
    config.save(update_fields=["billing_app_enabled"])
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    flight.tow_cost_actual = Decimal("20.00")
    flight.save(update_fields=["tow_cost_actual"])
    logsheet_with_flights.finalized = True
    logsheet_with_flights.save(update_fields=["finalized"])
    active_member.treasurer = True
    active_member.save(update_fields=["treasurer"])
    post_flight_charges(
        flight=flight,
        actor=active_member,
        allocations=get_billing_allocations(flight),
    )

    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:update_flight_split", args=[flight.pk]),
        {
            "split_with": active_member.pk,
            "split_type": "even",
            "reason": "Corrected payer allocation",
        },
    )

    assert response.status_code == 400
    assert "cannot request a split with yourself" in response.json()["error"]
    assert not FlightSplitRequest.objects.filter(flight=flight).exists()


@pytest.mark.django_db
def test_closing_period_locks_pending_split_requests(
    active_member, another_member, logsheet_with_flights
):
    active_member.treasurer = True
    active_member.save(update_fields=["treasurer"])
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    split_request = FlightSplitRequest.objects.create(
        flight=flight,
        requester=active_member,
        requested_member=another_member,
        split_type="even",
        allocation_version=1,
        expires_at=timezone.now() + timedelta(days=7),
    )

    close_period(
        year=flight.logsheet.log_date.year,
        month=flight.logsheet.log_date.month,
        actor=active_member,
        reason="Month reconciled",
    )

    split_request.refresh_from_db()
    assert split_request.status == FlightSplitRequest.Status.LOCKED


@pytest.mark.django_db
def test_treasurer_can_accept_locked_split_request_with_reason(
    client, active_member, another_member, logsheet_with_flights
):
    config = SiteConfiguration.objects.first() or SiteConfiguration.objects.create(
        club_name="Split Correction Test Club",
        domain_name="split-correction.example.com",
        club_abbreviation="SCT",
    )
    config.billing_app_enabled = True
    config.save(update_fields=["billing_app_enabled"])
    flight = Flight.objects.filter(logsheet=logsheet_with_flights).first()
    flight.tow_cost_actual = Decimal("20.00")
    flight.rental_cost_actual = Decimal("10.00")
    flight.save(update_fields=["tow_cost_actual", "rental_cost_actual"])
    logsheet_with_flights.finalized = True
    logsheet_with_flights.save(update_fields=["finalized"])
    active_member.treasurer = True
    active_member.save(update_fields=["treasurer"])

    post_flight_charges(
        flight=flight,
        actor=active_member,
        allocations=get_billing_allocations(flight),
    )
    initial_entry_count = LedgerEntry.objects.filter(flight=flight).count()

    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:update_flight_split", args=[flight.pk]),
        {
            "split_with": another_member.pk,
            "split_type": "rental",
            "reason": "Corrected payer allocation",
        },
    )
    assert response.status_code == 200
    split_request = FlightSplitRequest.objects.get(flight=flight)
    assert split_request.status == FlightSplitRequest.Status.PENDING

    close_period(
        year=flight.logsheet.log_date.year,
        month=flight.logsheet.log_date.month,
        actor=active_member,
        reason="Month reconciled",
    )
    split_request.refresh_from_db()
    assert split_request.status == FlightSplitRequest.Status.LOCKED

    response = client.post(
        reverse("logsheet:flight_split_request_detail", args=[split_request.token]),
        {"decision": "accept", "treasurer_reason": "Approved post-close correction"},
    )
    assert response.status_code == 302
    split_request.refresh_from_db()
    assert split_request.status == FlightSplitRequest.Status.ACCEPTED
    assert LedgerEntry.objects.filter(flight=flight).count() == initial_entry_count + 2
    assert LedgerEntry.objects.filter(kind=LedgerEntry.Kind.REVERSAL).count() == 2
    assert set(
        FlightChargeSnapshot.objects.filter(flight=flight).values_list(
            "allocation_version", flat=True
        )
    ) == {1, 2}


@pytest.mark.django_db
def test_split_request_model_rejects_self_as_partner(
    active_member, logsheet_with_flights
):
    with pytest.raises(ValidationError, match="cannot request a split with themselves"):
        FlightSplitRequest.objects.create(
            flight=Flight.objects.filter(logsheet=logsheet_with_flights).first(),
            requester=active_member,
            requested_member=active_member,
            split_type="even",
            allocation_version=1,
            expires_at=timezone.now() + timedelta(days=7),
        )


@pytest.mark.django_db
def test_split_request_can_be_cancelled_or_expires(
    client, active_member, another_member, logsheet_with_flights
):
    request = FlightSplitRequest.objects.create(
        flight=Flight.objects.filter(logsheet=logsheet_with_flights).first(),
        requester=active_member,
        requested_member=another_member,
        split_type="even",
        allocation_version=1,
        expires_at=timezone.now() + timedelta(days=7),
    )
    client.force_login(active_member)
    response = client.post(
        reverse("logsheet:flight_split_request_detail", args=[request.token]),
        {"decision": "cancel"},
    )
    assert response.status_code == 302
    request.refresh_from_db()
    assert request.status == FlightSplitRequest.Status.CANCELLED

    request.status = FlightSplitRequest.Status.PENDING
    request.expires_at = timezone.now() - timedelta(seconds=1)
    request.save(update_fields=["status", "expires_at"])
    client.force_login(another_member)
    client.post(
        reverse("logsheet:flight_split_request_detail", args=[request.token]),
        {"decision": "accept"},
    )
    request.refresh_from_db()
    assert request.status == FlightSplitRequest.Status.EXPIRED


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

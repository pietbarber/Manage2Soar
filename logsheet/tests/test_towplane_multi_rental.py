"""
Tests for Issue #968 — multiple towplane renters per closeout.

Covers:
- ``TowplaneRentalCharge`` model: cost / cost_display / ordering.
- ``TowplaneCloseout.total_rental_hours`` / ``rental_cost`` aggregation
  across multiple charge rows, plus fallback to the legacy scalar.
- ``TowplaneRentalChargeFormSet``: multi-row save, blank-row skipping,
  unique-per-(closeout, member) enforcement.
- Finance view attribution: per-renter charges land in the correct
  member's ``member_charges`` bucket.
- Legacy fallback path: closeouts that pre-date the migration (scalar
  only) still attribute to the legacy renter.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from logsheet.forms import TowplaneRentalChargeFormSet
from logsheet.models import (
    Airfield,
    Logsheet,
    LogsheetCloseout,
    Towplane,
    TowplaneCloseout,
    TowplaneRentalCharge,
)
from members.models import Member
from siteconfig.models import SiteConfiguration


def _make_member(username: str, first: str, last: str) -> Member:
    return Member.objects.create_user(
        username=username,
        password="testpass",
        first_name=first,
        last_name=last,
        membership_status="Full Member",
        duty_officer=True,
        email=f"{username}@example.com",
    )


class TowplaneRentalChargeModelTestCase(TestCase):
    """Model-level behaviour for the new child model."""

    def setUp(self):
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
            allow_towplane_rental=True,
        )
        self.member_a = _make_member("member-a", "Alice", "Aardvark")
        self.member_b = _make_member("member-b", "Bob", "Bear")
        self.towplane = Towplane.objects.create(
            name="Husky",
            n_number="N6085S",
            hourly_rental_rate=Decimal("95.00"),
        )
        self.airfield = Airfield.objects.create(identifier="KFRR", name="Front Royal")
        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-21", airfield=self.airfield, created_by=self.member_a
        )
        self.closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.0"),
            end_tach=Decimal("105.0"),
            fuel_added=Decimal("25.0"),
        )

    def test_cost_and_display_for_single_charge(self):
        charge = TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("2.0"),
        )
        self.assertEqual(charge.cost, Decimal("190.00"))
        self.assertEqual(charge.cost_display, "$190.00")

    def test_total_rental_hours_sums_all_charge_rows(self):
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("1.5"),
        )
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_b,
            hours=Decimal("2.5"),
        )
        self.assertEqual(self.closeout.total_rental_hours, Decimal("4.0"))
        # 4.0 * $95.00 = $380.00
        self.assertEqual(self.closeout.rental_cost, Decimal("380.00"))
        self.assertEqual(self.closeout.rental_cost_display, "$380.00")

    def test_total_rental_hours_falls_back_to_legacy_scalar(self):
        # No charge rows, but the legacy scalar is set (pre-migration data).
        self.closeout.rental_hours_chargeable = Decimal("3.0")
        self.closeout.rental_charged_to = self.member_a
        self.closeout.save()

        self.assertEqual(self.closeout.total_rental_hours, Decimal("3.0"))
        # 3.0 * $95.00 = $285.00
        self.assertEqual(self.closeout.rental_cost, Decimal("285.00"))

    def test_charge_rows_take_precedence_over_legacy_scalar(self):
        # Both a legacy scalar AND a charge row exist. The per-renter
        # rows should win, so the cost is based on the charge row's hours.
        self.closeout.rental_hours_chargeable = Decimal("3.0")
        self.closeout.save()
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("1.0"),
        )
        # 1.0 * $95.00 = $95.00 (not 3.0 * $95.00)
        self.assertEqual(self.closeout.rental_cost, Decimal("95.00"))

    def test_zero_hour_charge_yields_no_rental_cost(self):
        self.closeout.rental_hours_chargeable = Decimal("3.0")
        self.closeout.save()
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("0.0"),
        )
        # Zero hours on the only charge row -> no legacy fallback either.
        self.assertIsNone(self.closeout.rental_cost)

    def test_charge_rows_ordered_by_member_name(self):
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_b,  # "Bear"
            hours=Decimal("1.0"),
        )
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,  # "Aardvark"
            hours=Decimal("2.0"),
        )
        ordered = list(self.closeout.rental_charges.all())
        self.assertEqual(ordered[0].member, self.member_a)
        self.assertEqual(ordered[1].member, self.member_b)

    def test_unique_constraint_prevents_duplicate_member_for_closeout(self):
        from django.db import IntegrityError, transaction

        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("1.0"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TowplaneRentalCharge.objects.create(
                    closeout=self.closeout,
                    member=self.member_a,
                    hours=Decimal("2.0"),
                )


class TowplaneRentalChargeFormSetTestCase(TestCase):
    """Formset-level behaviour."""

    def setUp(self):
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
            allow_towplane_rental=True,
        )
        self.member_a = _make_member("member-a", "Alice", "Aardvark")
        self.member_b = _make_member("member-b", "Bob", "Bear")
        self.towplane = Towplane.objects.create(
            name="Husky",
            n_number="N6085S",
            hourly_rental_rate=Decimal("95.00"),
        )
        self.airfield = Airfield.objects.create(identifier="KFRR", name="Front Royal")
        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-21", airfield=self.airfield, created_by=self.member_a
        )
        self.closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.0"),
            end_tach=Decimal("105.0"),
            fuel_added=Decimal("25.0"),
        )

    def test_formset_saves_two_renter_rows(self):
        form_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-member": self.member_a.pk,
            "form-0-hours": "1.5",
            "form-1-member": self.member_b.pk,
            "form-1-hours": "2.5",
        }
        formset = TowplaneRentalChargeFormSet(
            data=form_data,
            queryset=TowplaneRentalCharge.objects.filter(closeout=self.closeout),
            prefix="form",
        )
        for f in formset.forms:
            f.instance.closeout = self.closeout
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()

        charges = list(self.closeout.rental_charges.all())
        self.assertEqual(len(charges), 2)
        self.assertEqual(self.closeout.total_rental_hours, Decimal("4.0"))

    def test_formset_skips_fully_blank_rows(self):
        """A fully blank extra row (no member, no hours) must be skipped."""
        form_data = {
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-member": self.member_a.pk,
            "form-0-hours": "1.0",
            "form-1-member": "",
            "form-1-hours": "",
        }
        formset = TowplaneRentalChargeFormSet(
            data=form_data,
            queryset=TowplaneRentalCharge.objects.filter(closeout=self.closeout),
            prefix="form",
        )
        for f in formset.forms:
            f.instance.closeout = self.closeout
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.closeout.rental_charges.count(), 1)

    def test_formset_deletes_marked_rows(self):
        existing = TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("1.0"),
        )
        form_data = {
            "form-TOTAL_FORMS": "1",
            "form-INITIAL_FORMS": "1",
            "form-MIN_NUM_FORMS": "0",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-id": existing.pk,
            "form-0-member": self.member_a.pk,
            "form-0-hours": "1.0",
            "form-0-DELETE": "on",
        }
        formset = TowplaneRentalChargeFormSet(
            data=form_data,
            queryset=TowplaneRentalCharge.objects.filter(closeout=self.closeout),
            prefix="form",
        )
        for f in formset.forms:
            f.instance.closeout = self.closeout
        self.assertTrue(formset.is_valid(), formset.errors)
        formset.save()
        self.assertEqual(self.closeout.rental_charges.count(), 0)


class FinanceAttributionMultiRenterTestCase(TestCase):
    """Finance view attributes per-renter charges to the correct member."""

    def setUp(self):
        self.config = SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.com",
            club_abbreviation="TC",
            allow_towplane_rental=True,
        )
        self.member_a = _make_member("member-a", "Alice", "Aardvark")
        self.member_b = _make_member("member-b", "Bob", "Bear")
        self.towplane = Towplane.objects.create(
            name="Husky",
            n_number="N6085S",
            hourly_rental_rate=Decimal("95.00"),
        )
        self.airfield = Airfield.objects.create(identifier="KFRR", name="Front Royal")
        self.logsheet = Logsheet.objects.create(
            log_date="2025-11-21",
            airfield=self.airfield,
            created_by=self.member_a,
            duty_officer=self.member_a,
        )
        self.closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=Decimal("100.0"),
            end_tach=Decimal("105.0"),
            fuel_added=Decimal("25.0"),
        )
        # LogsheetPayment rows for both members (so finalize isn't blocked).
        from logsheet.models import LogsheetPayment

        LogsheetPayment.objects.create(
            logsheet=self.logsheet,
            member=self.member_a,
            payment_method="cash",
        )
        LogsheetPayment.objects.create(
            logsheet=self.logsheet,
            member=self.member_b,
            payment_method="cash",
        )
        # LogsheetCloseout required for the finalize branch.
        LogsheetCloseout.objects.create(logsheet=self.logsheet)

    @staticmethod
    def _charge_map(response):
        """Convert the view's ``member_charges_sorted`` list into a dict."""
        return {m: v for m, v in response.context["member_charges_sorted"]}

    def test_per_renter_attribution(self):
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("1.5"),
        )
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_b,
            hours=Decimal("2.5"),
        )

        self.client.force_login(self.member_a)
        url = reverse("logsheet:manage_logsheet_finances", args=[self.logsheet.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        member_charges = self._charge_map(response)
        self.assertEqual(
            member_charges[self.member_a]["towplane_rental"], Decimal("142.50")
        )
        self.assertEqual(
            member_charges[self.member_b]["towplane_rental"], Decimal("237.50")
        )
        # Totals: 1.5 + 2.5 = 4.0 hours * $95.00 = $380.00
        self.assertEqual(response.context["total_towplane_rental"], Decimal("380.00"))

    def test_legacy_scalar_fallback_attribution(self):
        """Pre-migration closeouts (scalar only) still attribute correctly."""
        self.closeout.rental_hours_chargeable = Decimal("2.0")
        self.closeout.rental_charged_to = self.member_a
        self.closeout.save()

        self.client.force_login(self.member_a)
        url = reverse("logsheet:manage_logsheet_finances", args=[self.logsheet.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        member_charges = self._charge_map(response)
        # 2.0 hours * $95.00 = $190.00
        self.assertEqual(
            member_charges[self.member_a]["towplane_rental"], Decimal("190.00")
        )
        self.assertEqual(response.context["total_towplane_rental"], Decimal("190.00"))

    def test_responsible_members_includes_all_renters(self):
        """Both per-renter members are responsible and require a payment method."""
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_a,
            hours=Decimal("1.0"),
        )
        TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_b,
            hours=Decimal("1.0"),
        )

        # The view auto-creates LogsheetPayment rows (default payment_method
        # = "account") for any member in member_charges who doesn't have one.
        # To trigger the "missing payment method" finalize block, we need to
        # blank member_b's payment_method AFTER the auto-creation runs.
        # A GET request triggers the auto-creation; then we blank it.
        from logsheet.models import LogsheetPayment

        self.client.force_login(self.member_a)
        url = reverse("logsheet:manage_logsheet_finances", args=[self.logsheet.pk])
        self.client.get(url)  # Triggers auto-creation of missing payments

        # Now blank member_b's payment method to trigger the missing branch.
        payment = LogsheetPayment.objects.get(
            logsheet=self.logsheet, member=self.member_b
        )
        payment.payment_method = None
        payment.save(update_fields=["payment_method"])

        # Finalization should now be blocked.
        response = self.client.post(
            url,
            {"finalize": "1"},
            follow=True,
        )
        self.assertContains(response, "Missing payment method")
        self.assertContains(response, "Bob Bear")

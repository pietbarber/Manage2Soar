"""
E2E tests for the per-renter towplane rental charge rows (Issue #968).

Verifies the "Add Renter" / "Remove renter" controls on the edit-closeout
page actually work in a real browser:

1. Clicking "Add Renter" appends a new, correctly-reindexed rental row
   (field names point at the next formset index, TOTAL_FORMS increments).
2. Clicking the trashcan on a freshly-added (unsaved) row removes it.
3. Clicking the trashcan on an existing (saved) row toggles the formset
   DELETE checkbox without removing the row from the DOM.

These guard against the regression where the button appeared but did
nothing (the "Add Renter" handler bailed out on a broken DOM lookup).
"""

from datetime import date

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import (
    Airfield,
    Logsheet,
    Towplane,
    TowplaneCloseout,
    TowplaneRentalCharge,
)
from siteconfig.models import SiteConfiguration


class TestTowplaneRentalRenters(DjangoPlaywrightTestCase):
    """E2E tests for the add/remove renter controls on the closeout page."""

    def setUp(self):
        super().setUp()
        self.member = self.create_test_member(username="renterpilot", is_superuser=True)
        self.member_b = self.create_test_member(
            username="renterbob", is_superuser=False
        )

        config = SiteConfiguration.objects.first()
        if config:
            config.allow_towplane_rental = True
            config.save(update_fields=["allow_towplane_rental"])
        else:
            SiteConfiguration.objects.create(
                club_name="Test Club",
                domain_name="test.example.com",
                club_abbreviation="TC",
                allow_towplane_rental=True,
            )

        self.airfield = Airfield.objects.create(
            identifier="KRRD", name="Renters Airfield", is_active=True
        )
        self.towplane = Towplane.objects.create(
            name="Rental Husky",
            n_number="N968RR",
            is_active=True,
            club_owned=True,
            hourly_rental_rate=150.00,
        )
        # A second, unused towplane keeps "available_towplanes" non-empty so
        # the rental section (which also shows the add-towplane card) renders.
        self.towplane_2 = Towplane.objects.create(
            name="Spare Cub",
            n_number="N2CUB",
            is_active=True,
            club_owned=True,
            hourly_rental_rate=120.00,
        )

        self.logsheet = Logsheet.objects.create(
            log_date=date(2026, 1, 15),
            airfield=self.airfield,
            created_by=self.member,
            duty_officer=self.member,
        )
        # An existing closeout drives the per-closeout rental formset in the UI.
        self.closeout = TowplaneCloseout.objects.create(
            logsheet=self.logsheet,
            towplane=self.towplane,
            start_tach=100.0,
            end_tach=105.0,
            fuel_added=25.0,
        )
        # A saved renter so there is an existing row with a DELETE checkbox.
        self.existing_charge = TowplaneRentalCharge.objects.create(
            closeout=self.closeout,
            member=self.member_b,
            hours=1.5,
        )

        self.login(username="renterpilot")

        from django.urls import reverse

        self.url = f"{self.live_server_url}{reverse('logsheet:edit_logsheet_closeout', kwargs={'pk': self.logsheet.pk})}"

    # ------------------------------------------------------------------
    # Add renter
    # ------------------------------------------------------------------

    def test_add_renter_appends_reindexed_row(self):
        """Clicking 'Add Renter' appends a new row with the next index."""
        self.page.goto(self.url)

        # The management form (with TOTAL_FORMS) is a sibling of the list,
        # so scope it to the enclosing column rather than the list itself.
        card = self.page.locator(".add-rental-charge").first.locator(
            "xpath=ancestor::div[contains(@class, 'col-')][1]"
        )
        list_el = card.locator(".rental-charges-list")
        total_input = card.locator('input[name$="-TOTAL_FORMS"]').first

        initial_count = list_el.locator(".rental-charge-row").count()
        initial_total = int(total_input.input_value())
        self.assertEqual(initial_total, initial_count)

        # There should be at least the saved renter plus one blank placeholder.
        self.assertGreaterEqual(initial_count, 2)

        self.page.locator(".add-rental-charge").first.click()

        new_count = list_el.locator(".rental-charge-row").count()
        self.assertEqual(new_count, initial_count + 1)

        new_total = int(total_input.input_value())
        self.assertEqual(new_total, initial_total + 1)

        # The newly-added row must be reindexed to the next index (rc-0-<n>-member).
        new_index = int(initial_total)
        member_field = self.page.locator(
            f'.rental-charge-row [name="rc-0-{new_index}-member"]'
        )
        self.assertGreater(member_field.count(), 0)

    # ------------------------------------------------------------------
    # Remove renter (unsaved row)
    # ------------------------------------------------------------------

    def test_remove_unsaved_renter_row(self):
        """Trashcan on a freshly-added row removes it from the DOM."""
        self.page.goto(self.url)

        list_el = self.page.locator(".rental-charges-list")
        count_before = list_el.locator(".rental-charge-row").count()

        # Add a brand-new (unsaved) row.
        self.page.locator(".add-rental-charge").first.click()
        self.assertEqual(
            list_el.locator(".rental-charge-row").count(), count_before + 1
        )

        # Trashcan on the last (newest) row removes it.
        self.page.locator(".rental-charge-row").last.locator(
            ".rental-row-delete"
        ).click()
        self.assertEqual(list_el.locator(".rental-charge-row").count(), count_before)

    # ------------------------------------------------------------------
    # Remove renter (saved row)
    # ------------------------------------------------------------------

    def test_remove_saved_renter_toggles_delete_flag(self):
        """Trashcan on a saved row toggles the formset DELETE checkbox."""
        self.page.goto(self.url)

        # The saved renter (Bob) row is the first row and carries the flag.
        saved_row = self.page.locator(".rental-charge-row").first
        flag = saved_row.locator(".rental-row-delete-flag")
        self.assertTrue(flag.count() >= 1)
        self.assertFalse(flag.first.is_checked())

        # Clicking the trashcan marks the row for deletion (flag toggled on).
        saved_row.locator(".rental-row-delete").click()
        self.assertTrue(flag.first.is_checked())
        # Row stays in the DOM (it is a saved record, not a temp row).
        self.assertTrue(self.page.locator(".rental-charge-row").first.count() >= 1)

        # Clicking again un-marks it.
        saved_row.locator(".rental-row-delete").click()
        self.assertFalse(flag.first.is_checked())

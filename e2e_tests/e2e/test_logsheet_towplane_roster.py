"""Browser coverage for day-level towplane roster interactions."""

from datetime import date, timedelta
from decimal import Decimal

from django.urls import reverse

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import (
    Airfield,
    Logsheet,
    LogsheetTowplane,
    Towplane,
    TowplaneCloseout,
)
from siteconfig.models import SiteConfiguration


class TestLogsheetTowplaneRoster(DjangoPlaywrightTestCase):
    """Verify roster JavaScript works in the browser, not just server tests."""

    def setUp(self):
        super().setUp()
        self.member = self.create_test_member(
            username="rosterbrowser",
            is_superuser=True,
            towpilot=True,
        )
        self.member_b = self.create_test_member(
            username="rosterbrowserb",
            towpilot=True,
        )
        SiteConfiguration.objects.create(
            club_name="Browser Club",
            domain_name="browser.example.com",
            club_abbreviation="BRC",
        )
        self.airfield = Airfield.objects.create(
            identifier="KWEB",
            name="Browser Airfield",
            is_active=True,
        )
        self.towplane_a = Towplane.objects.create(
            name="Browser Husky",
            n_number="N1WEB",
            is_active=True,
            club_owned=True,
        )
        self.towplane_b = Towplane.objects.create(
            name="Browser Cub",
            n_number="N2WEB",
            is_active=True,
            club_owned=True,
        )
        prior_logsheet = Logsheet.objects.create(
            log_date=date.today() - timedelta(days=1),
            airfield=self.airfield,
            created_by=self.member,
        )
        TowplaneCloseout.objects.create(
            logsheet=prior_logsheet,
            towplane=self.towplane_b,
            end_tach=Decimal("325.00"),
        )
        self.current_logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.member,
        )
        LogsheetTowplane.objects.create(
            logsheet=self.current_logsheet,
            towplane=self.towplane_a,
            tow_pilot=self.member,
            start_tach=Decimal("111.00"),
        )
        LogsheetTowplane.objects.create(
            logsheet=self.current_logsheet,
            towplane=self.towplane_b,
            tow_pilot=self.member_b,
            start_tach=Decimal("325.00"),
        )
        self.current_logsheet.default_towplane = self.towplane_a
        self.current_logsheet.save(update_fields=["default_towplane"])
        self.login(username="rosterbrowser")

    def test_create_roster_adds_one_blank_row_and_prefills_tach(self):
        self.page.goto(f"{self.live_server_url}{reverse('logsheet:create')}")
        self.page.locator("#createLogsheetModal").wait_for(state="attached")
        self.page.get_by_role("button", name="Create New Logsheet").first.click()

        total = self.page.locator('input[name="towplanes-TOTAL_FORMS"]')
        rows = self.page.locator(".towplane-row")
        self.assertEqual(int(total.input_value()), 1)
        self.assertEqual(rows.count(), 1)

        rows.nth(0).locator('select[name$="-towplane"]').select_option(
            str(self.towplane_a.pk)
        )
        self.page.locator('input[name="towplanes-0-start_tach"]').fill("111.00")

        self.page.locator("#addTowplaneRow").click()
        self.assertEqual(int(total.input_value()), 2)
        self.assertEqual(rows.count(), 2)
        self.assertEqual(
            self.page.locator('select[name="towplanes-1-towplane"]').input_value(),
            "",
        )
        self.assertEqual(
            self.page.locator('input[name="towplanes-1-start_tach"]').input_value(),
            "",
        )

        rows.nth(1).locator('select[name$="-towplane"]').select_option(
            str(self.towplane_b.pk)
        )
        self.page.wait_for_function(
            """
            () => document.querySelector('input[name="towplanes-1-start_tach"]').value === '325.00'
            """
        )

        # A second click must append one more uniquely indexed blank row.
        self.page.locator("#addTowplaneRow").click()
        self.assertEqual(int(total.input_value()), 3)
        self.assertEqual(rows.count(), 3)
        self.assertEqual(
            self.page.locator('select[name="towplanes-2-towplane"]').input_value(),
            "",
        )
        self.assertEqual(
            self.page.locator('input[name="towplanes-2-start_tach"]').input_value(),
            "",
        )

    def test_closeout_roster_reindexes_repeated_added_rows(self):
        self.page.goto(
            f"{self.live_server_url}{reverse('logsheet:edit_logsheet_closeout', kwargs={'pk': self.current_logsheet.pk})}"
        )

        section = self.page.locator("#add-roster-row").locator(
            "xpath=ancestor::div[contains(@class, 'form-section')][1]"
        )
        rows = section.locator(".row.g-2")
        total = self.page.locator('input[name="roster-TOTAL_FORMS"]')
        initial_total = int(total.input_value())

        self.page.locator("#add-roster-row").click()
        self.page.locator("#add-roster-row").click()

        self.assertEqual(int(total.input_value()), initial_total + 2)
        self.assertEqual(rows.count(), initial_total + 2)
        self.assertEqual(
            section.locator(f'select[name="roster-{initial_total}-towplane"]').count(),
            1,
        )
        self.assertEqual(
            section.locator(
                f'select[name="roster-{initial_total + 1}-towplane"]'
            ).count(),
            1,
        )
        self.assertEqual(
            section.locator(
                f'input[name="roster-{initial_total + 1}-start_tach"]'
            ).input_value(),
            "",
        )

    def test_flight_modal_applies_roster_pilot_and_preserves_override(self):
        self.page.goto(
            f"{self.live_server_url}{reverse('logsheet:manage', kwargs={'pk': self.current_logsheet.pk})}"
        )
        self.page.locator('a[data-url*="/add-flight/"]').first.click()

        towplane = self.page.locator("#flightModalContent #id_towplane")
        tow_pilot = self.page.locator("#flightModalContent #id_tow_pilot")
        towplane.wait_for(state="visible")

        # The default towplane is already selected, so no user plane change
        # occurs; the initializer must still apply the roster pilot.
        self.assertEqual(towplane.input_value(), str(self.towplane_a.pk))
        self.assertEqual(tow_pilot.input_value(), str(self.member.pk))

        # Override plane A's pilot, switch to B, and switch back to A.
        tow_pilot.select_option(str(self.member_b.pk))
        towplane.select_option(str(self.towplane_b.pk))
        self.assertEqual(tow_pilot.input_value(), str(self.member_b.pk))
        towplane.select_option(str(self.towplane_a.pk))
        self.assertEqual(tow_pilot.input_value(), str(self.member_b.pk))

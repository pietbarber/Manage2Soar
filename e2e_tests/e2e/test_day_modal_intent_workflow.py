"""E2E coverage for duty day modal accordion + intent workflow interactions.

Validates primary modal interactions introduced in the phase-1 UX refactor:
- key accordions render collapsed by default
- opening "I Plan to Fly This Day" reveals the inline form
- submitting intent updates the modal DOM via HTMX
- cancelling intent restores the inline form path
"""

from datetime import date, timedelta

from duty_roster.models import DutyAssignment
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestDayModalIntentWorkflow(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        config, _ = SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )
        config.allow_glider_reservations = True
        config.max_reservations_per_year = 3
        config.save(
            update_fields=["allow_glider_reservations", "max_reservations_per_year"]
        )

    def test_modal_accordions_and_intent_htmx_flow(self):
        self.create_test_member(
            username="modalmember",
            email="modalmember@example.com",
            membership_status="Full Member",
        )
        self.login(username="modalmember")

        ops_day = date.today() + timedelta(days=7)
        DutyAssignment.objects.create(date=ops_day)

        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("#calendar-body")

        day_cell = self.page.locator(
            f'td[hx-get="/duty_roster/calendar/day/{ops_day.year}/{ops_day.month}/{ops_day.day}/"]'
        )
        day_cell.first.click()

        self.page.wait_for_selector("#modal-body")
        self.page.wait_for_selector("#plan-to-fly-panel", state="attached")
        self.page.wait_for_selector("#reserve-glider-panel", state="attached")

        plan_panel = self.page.locator("#plan-to-fly-panel")
        reserve_panel = self.page.locator("#reserve-glider-panel")

        # Accordions start collapsed by default
        assert "show" not in (plan_panel.get_attribute("class") or "")
        assert "show" not in (reserve_panel.get_attribute("class") or "")

        # Open plan-to-fly accordion and submit intent
        self.page.locator('button[data-bs-target="#plan-to-fly-panel"]').click()
        self.page.wait_for_selector('input[name="available_as"][value="club_single"]')
        self.page.check('input[name="available_as"][value="club_single"]')
        self.page.click('button:has-text("Submit Intent")')

        self.page.wait_for_selector("text=planning to fly this day")

        # Cancel intent and verify form path is restored
        self.page.click('button:has-text("Cancel Intent")')
        self.page.wait_for_selector("text=removed your intent to fly")
        self.page.wait_for_selector('input[name="available_as"][value="club_single"]')

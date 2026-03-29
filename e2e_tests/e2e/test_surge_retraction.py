from datetime import date, timedelta

from duty_roster.models import DutyAssignment
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestSurgeRetraction(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
                "schedule_instructors": True,
                "schedule_tow_pilots": True,
            }
        )

    def test_modal_allows_surge_instructor_to_retract_offer(self):
        primary = self.create_test_member(
            username="surge_primary",
            instructor=True,
            membership_status="Full Member",
        )
        surge = self.create_test_member(
            username="surge_volunteer",
            instructor=True,
            membership_status="Full Member",
        )

        target_day = date.today() + timedelta(days=10)
        assignment = DutyAssignment.objects.create(
            date=target_day,
            instructor=primary,
            surge_instructor=surge,
        )

        self.login(username="surge_volunteer")
        self.page.goto(
            f"{self.live_server_url}/duty_roster/calendar/{target_day.year}/{target_day.month}/"
        )
        self.page.wait_for_selector("#calendar-body")

        day_cell = self.page.locator(
            f'td[hx-get="/duty_roster/calendar/day/{target_day.year}/{target_day.month}/{target_day.day}/"]'
        )
        day_cell.first.click()

        self.page.wait_for_selector("#modal-body")
        retract_link = self.page.locator(
            f'a[href="/duty_roster/instruction/retract-surge/{assignment.id}/"]'
        )
        assert retract_link.is_visible()

        retract_link.click()
        self.page.wait_for_url(
            f"{self.live_server_url}/duty_roster/instruction/retract-surge/{assignment.id}/"
        )
        self.page.wait_for_selector("text=Retract Surge Instructor Offer")

        self.page.get_by_role("button", name="Yes, Retract Offer").click()
        self.page.wait_for_url(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("text=retracted your surge instructor offer")

        assignment.refresh_from_db()
        assert assignment.surge_instructor is None

    def test_modal_allows_surge_tow_pilot_to_retract_offer(self):
        primary = self.create_test_member(
            username="surge_tow_primary",
            towpilot=True,
            membership_status="Full Member",
        )
        surge = self.create_test_member(
            username="surge_tow_volunteer",
            towpilot=True,
            membership_status="Full Member",
        )

        target_day = date.today() + timedelta(days=11)
        assignment = DutyAssignment.objects.create(
            date=target_day,
            tow_pilot=primary,
            surge_tow_pilot=surge,
        )

        self.login(username="surge_tow_volunteer")
        self.page.goto(
            f"{self.live_server_url}/duty_roster/calendar/{target_day.year}/{target_day.month}/"
        )
        self.page.wait_for_selector("#calendar-body")

        day_cell = self.page.locator(
            f'td[hx-get="/duty_roster/calendar/day/{target_day.year}/{target_day.month}/{target_day.day}/"]'
        )
        day_cell.first.click()

        self.page.wait_for_selector("#modal-body")
        retract_link = self.page.locator(
            f'a[href="/duty_roster/tow/retract-surge/{assignment.id}/"]'
        )
        assert retract_link.is_visible()

        retract_link.click()
        self.page.wait_for_url(
            f"{self.live_server_url}/duty_roster/tow/retract-surge/{assignment.id}/"
        )
        self.page.wait_for_selector("text=Retract Surge Tow Pilot Offer")

        self.page.get_by_role("button", name="Yes, Retract Offer").click()
        self.page.wait_for_url(f"{self.live_server_url}/duty_roster/calendar/")
        self.page.wait_for_selector("text=retracted your surge tow pilot offer")

        assignment.refresh_from_db()
        assert assignment.surge_tow_pilot is None

"""
E2E coverage for Issue #1053 – Duty Roster volunteer fill redirect.

After a member clicks "Volunteer to fill" from a calendar day cell and
confirms, the browser must land on the duty day detail page for that date
(not jump back to the current-month calendar).  The flow under test:

    calendar (month view) → day cell → modal → "Volunteer to fill"
      → confirmation page → "Yes, I'll fill this role"
      → duty day detail page (NOT /duty_roster/calendar/)
"""

from datetime import date, timedelta

from duty_roster.models import DutyAssignment
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestVolunteerFillRedirect(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        config, _ = SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
            }
        )
        config.schedule_instructors = True
        config.schedule_tow_pilots = True
        config.save(update_fields=["schedule_instructors", "schedule_tow_pilots"])

    def _open_modal_for(self, target_day: date, assignment: DutyAssignment):
        """Navigate to the month containing ``target_day`` and open its modal."""
        self.page.goto(
            f"{self.live_server_url}/duty_roster/calendar/"
            f"{target_day.year}/{target_day.month}/"
        )
        self.page.wait_for_selector("#calendar-body")

        day_cell = self.page.locator(
            f'td[hx-get="/duty_roster/calendar/day/'
            f'{target_day.year}/{target_day.month}/{target_day.day}/"]'
        )
        day_cell.first.click()
        self.page.wait_for_selector("#modal-body")

    def test_volunteer_fill_returns_to_day_detail_page(self):
        """
        Issue #1053: after confirming the volunteer, the browser is at the
        day detail page for the target date — not the current-month calendar.
        """
        self.create_test_member(
            username="volfill",
            instructor=True,
            membership_status="Full Member",
        )
        self.login(username="volfill")

        target_day = date.today() + timedelta(days=10)
        assignment = DutyAssignment.objects.create(date=target_day)

        self._open_modal_for(target_day, assignment)

        # Click the "Volunteer to fill" button for the instructor slot.
        volunteer_link = self.page.locator("a:has-text('Volunteer to fill')")
        assert volunteer_link.count() >= 1
        volunteer_link.first.click()

        # Confirmation page loaded.
        self.page.wait_for_selector("text=Volunteer to Fill Instructor")

        # Confirm.
        self.page.get_by_role("button", name="Yes, I'll fill this role").click()

        # Should land on the day detail page, NOT the bare calendar.
        day_detail_prefix = (
            f"{self.live_server_url}/duty_roster/calendar/day/"
            f"{target_day.year}/{target_day.month}/{target_day.day}/"
        )
        self.page.wait_for_url(day_detail_prefix)
        assert self.page.url.startswith(day_detail_prefix)
        # The bare calendar URL must NOT be the destination.
        assert self.page.url != (f"{self.live_server_url}/duty_roster/calendar/")

        assignment.refresh_from_db()
        assert assignment.instructor is not None

    def test_cancel_returns_to_day_detail_page(self):
        """
        Issue #1053: the "Cancel" button on the confirmation page should also
        return the member to the day detail page (not the bare calendar).
        """
        self.create_test_member(
            username="volcancel",
            instructor=True,
            membership_status="Full Member",
        )
        self.login(username="volcancel")

        target_day = date.today() + timedelta(days=12)
        assignment = DutyAssignment.objects.create(date=target_day)

        self._open_modal_for(target_day, assignment)

        volunteer_link = self.page.locator("a:has-text('Volunteer to fill')")
        assert volunteer_link.count() >= 1
        volunteer_link.first.click()

        self.page.wait_for_selector("text=Volunteer to Fill Instructor")

        day_detail_prefix = (
            f"{self.live_server_url}/duty_roster/calendar/day/"
            f"{target_day.year}/{target_day.month}/{target_day.day}/"
        )
        # Cancel is an anchor whose href points back to the day detail page.
        self.page.get_by_role("link", name="Cancel").click()
        self.page.wait_for_url(day_detail_prefix)
        assert self.page.url.startswith(day_detail_prefix)

        assignment.refresh_from_db()
        assert assignment.instructor is None

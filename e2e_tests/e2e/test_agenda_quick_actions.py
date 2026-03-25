"""E2E coverage for agenda quick actions (Issue #805)."""

from datetime import date, timedelta

from duty_roster.models import DutyAssignment, InstructionSlot
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestAgendaQuickActions(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            club_abbreviation="TSC",
            domain_name="test.org",
            schedule_duty_officers=True,
            allow_glider_reservations=False,
        )

    def test_request_swap_visible_for_assigned_crew_and_navigates(self):
        crew = self.create_test_member(
            username="agenda_do",
            duty_officer=True,
            membership_status="Full Member",
        )
        target_day = date.today() + timedelta(days=6)
        DutyAssignment.objects.create(date=target_day, duty_officer=crew)

        self.login(username="agenda_do")
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/?view=agenda")
        self.page.wait_for_selector("#agenda-view-content", state="visible")

        swap_link = self.page.locator("a:has-text('Request Swap')").first
        assert swap_link.is_visible()
        reserve_disabled = self.page.locator(
            "#agenda-view-content .agenda-disabled-trigger[data-bs-content*='Glider reservations are currently disabled.']"
        ).first
        assert reserve_disabled.is_visible()
        reserve_disabled.click()
        self.page.wait_for_selector(
            ".popover .popover-body:has-text('Glider reservations are currently disabled.')"
        )

        swap_link.click()
        self.page.wait_for_url("**/duty_roster/swap/request/create/**")

    def test_plan_to_fly_disabled_when_instruction_request_exists(self):
        student = self.create_test_member(
            username="agenda_student",
            membership_status="Full Member",
        )
        instructor = self.create_test_member(
            username="agenda_instructor",
            instructor=True,
            membership_status="Full Member",
        )
        target_day = date.today() + timedelta(days=6)
        assignment = DutyAssignment.objects.create(
            date=target_day, instructor=instructor
        )
        InstructionSlot.objects.create(assignment=assignment, student=student)

        self.login(username="agenda_student")
        self.page.goto(f"{self.live_server_url}/duty_roster/calendar/?view=agenda")
        self.page.wait_for_selector("#agenda-view-content", state="visible")

        disabled_trigger = self.page.locator(
            "#agenda-view-content .agenda-disabled-trigger[data-bs-content*='already requested instruction']"
        ).first
        assert disabled_trigger.is_visible()
        disabled_trigger.click()
        self.page.wait_for_selector(
            ".popover .popover-body:has-text('already requested instruction')"
        )

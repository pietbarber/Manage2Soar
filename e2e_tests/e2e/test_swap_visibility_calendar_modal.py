"""E2E coverage for open-swap visibility on calendar cells and day modal (Issue #946)."""

from datetime import date, timedelta

from django.urls import reverse

from duty_roster.models import DutyAssignment, DutySwapRequest
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestSwapVisibilityCalendarModal(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.get_or_create(
            defaults={
                "club_name": "Test Soaring Club",
                "club_abbreviation": "TSC",
                "domain_name": "test.org",
                "schedule_tow_pilots": True,
                "schedule_duty_officers": True,
                "schedule_instructors": True,
                "schedule_assistant_duty_officers": True,
            }
        )

    def test_open_swap_marker_and_day_modal_details_are_visible(self):
        requester = self.create_test_member(
            username="swap_marker_requester",
            email="swap_marker_requester@example.com",
            membership_status="Full Member",
            towpilot=True,
        )
        viewer = self.create_test_member(
            username="swap_marker_viewer",
            email="swap_marker_viewer@example.com",
            membership_status="Full Member",
            towpilot=True,
        )

        duty_date = date.today() + timedelta(days=10)
        DutyAssignment.objects.create(
            date=duty_date,
            tow_pilot=requester,
            is_scheduled=True,
        )

        swap_request = DutySwapRequest.objects.create(
            requester=requester,
            original_date=duty_date,
            role="TOW",
            request_type="general",
            status="open",
            notes="Need coverage for family event",
        )

        self.login(username=viewer.username)
        calendar_url = reverse(
            "duty_roster:duty_calendar_month",
            kwargs={"year": duty_date.year, "month": duty_date.month},
        )
        self.page.goto(f"{self.live_server_url}{calendar_url}")

        marker = self.page.locator("span.badge:has-text('1 open')").first
        marker.wait_for(state="visible")

        marker_cell = marker.locator("xpath=ancestor::td[1]")
        marker_cell.click()

        self.page.locator("#calendarModal").wait_for(state="visible")
        modal_body = self.page.locator("#modal-body")
        modal_body.locator("text=Open Swap Requests").wait_for(state="visible")

        assert modal_body.locator("text=Tow Pilot").count() >= 1
        assert (
            modal_body.locator("text=Requested by Test User").count() >= 1
            or modal_body.locator("text=Requested by").count() >= 1
        )

        detail_path = reverse("duty_roster:swap_request_detail", args=[swap_request.pk])
        assert modal_body.locator(f'a[href="{detail_path}"]').count() >= 1

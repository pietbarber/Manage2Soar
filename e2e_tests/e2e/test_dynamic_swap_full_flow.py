"""End-to-end dynamic swap workflow coverage for Phase F step 5.

Covers the full happy path:
- requester creates a dynamic-role swap request
- eligible member sees request in open requests and submits a swap offer
- requester accepts the offer
- normalized duty assignment rows are updated for both dates
"""

from datetime import date, timedelta

from django.urls import reverse

from duty_roster.models import (
    DutyAssignment,
    DutyAssignmentRole,
    DutyRoleDefinition,
    DutySwapOffer,
    DutySwapRequest,
)
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestDynamicSwapFullFlow(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        SiteConfiguration.objects.all().delete()
        SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            club_abbreviation="TSC",
            domain_name="test.org",
            schedule_tow_pilots=True,
            schedule_duty_officers=True,
            schedule_instructors=True,
            schedule_assistant_duty_officers=True,
            enable_dynamic_duty_roles=True,
        )

    def test_dynamic_swap_flow_request_offer_accept_updates_assignments(self):
        requester = self.create_test_member(
            username="dynamic_requester",
            email="dynamic_requester@example.com",
            membership_status="Full Member",
            towpilot=True,
        )
        offerer = self.create_test_member(
            username="dynamic_offerer",
            email="dynamic_offerer@example.com",
            membership_status="Full Member",
            towpilot=True,
        )

        role_definition = DutyRoleDefinition.objects.create(
            site_configuration=SiteConfiguration.objects.first(),
            key="launch_coord",
            display_name="Launch Coordinator",
            is_active=True,
            sort_order=10,
            legacy_role_key="towpilot",
        )
        role_definition.qualification_requirements.create(
            requirement_type="legacy_role_flag",
            requirement_value="towpilot",
            is_required=True,
        )

        original_date = date.today() + timedelta(days=14)
        proposed_swap_date = date.today() + timedelta(days=21)

        original_assignment = DutyAssignment.objects.create(
            date=original_date,
            tow_pilot=requester,
        )
        swap_assignment = DutyAssignment.objects.create(
            date=proposed_swap_date,
            tow_pilot=offerer,
        )

        DutyAssignmentRole.objects.create(
            assignment=original_assignment,
            role_key="launch_coord",
            member=requester,
            role_definition=role_definition,
            legacy_role_key="towpilot",
        )
        DutyAssignmentRole.objects.create(
            assignment=swap_assignment,
            role_key="launch_coord",
            member=offerer,
            role_definition=role_definition,
            legacy_role_key="towpilot",
        )

        # Step 1: requester creates a dynamic swap request from UI.
        self.login(username=requester.username)
        create_url = reverse(
            "duty_roster:create_swap_request",
            kwargs={
                "year": original_date.year,
                "month": original_date.month,
                "day": original_date.day,
                "role": "DYNAMIC",
            },
        )
        self.page.goto(
            f"{self.live_server_url}{create_url}?dynamic_role_key=launch_coord"
        )
        self.page.wait_for_selector("text=Request Coverage")
        self.page.check('input[name="request_type"][value="general"]')
        self.page.fill('textarea[name="notes"]', "Need launch coordinator coverage")
        self.page.get_by_role("button", name="Send Request").click()
        self.page.wait_for_url("**/duty_roster/swap/my-requests/**")

        swap_request = DutySwapRequest.objects.get(
            requester=requester,
            role="DYNAMIC",
            dynamic_role_key="launch_coord",
            status="open",
        )

        # Step 2: offerer sees request in open requests and submits swap offer.
        self.context.clear_cookies()
        self.login(username=offerer.username)
        self.page.goto(f"{self.live_server_url}/duty_roster/swap/open-requests/")
        self.page.wait_for_selector("text=Open Requests")
        make_offer_url = reverse("duty_roster:make_swap_offer", args=[swap_request.pk])
        self.page.wait_for_selector(f'a[href="{make_offer_url}"]')
        self.page.locator(f'a[href="{make_offer_url}"]').first.click()

        self.page.wait_for_selector("text=Make an Offer")
        self.page.check('input[name="offer_type"][value="swap"]')
        self.page.wait_for_function(
            "() => getComputedStyle(document.querySelector('#swap-date-section')).display !== 'none'"
        )
        self.page.fill(
            'input[name="proposed_swap_date"]', proposed_swap_date.isoformat()
        )
        self.page.fill(
            'textarea[name="notes"]', "Happy to trade launch coordinator dates"
        )
        self.page.get_by_role("button", name="Send Offer").click()

        detail_url = f"{self.live_server_url}{reverse('duty_roster:swap_request_detail', args=[swap_request.pk])}"
        self.page.wait_for_url(detail_url)
        self.page.wait_for_selector("text=Swap: Will take")

        offer = DutySwapOffer.objects.get(swap_request=swap_request, offered_by=offerer)
        assert offer.status == "pending"

        # Step 3: requester accepts and assignments update.
        self.context.clear_cookies()
        self.login(username=requester.username)
        self.page.goto(detail_url)
        self.page.wait_for_selector('button:has-text("Accept")')
        self.page.on("dialog", lambda dialog: dialog.accept())
        self.page.click('button:has-text("Accept")')
        self.page.wait_for_url("**/duty_roster/swap/my-requests/**")

        swap_request.refresh_from_db()
        offer.refresh_from_db()
        original_assignment.refresh_from_db()
        swap_assignment.refresh_from_db()

        original_row = DutyAssignmentRole.objects.get(
            assignment=original_assignment,
            role_key="launch_coord",
        )
        swap_row = DutyAssignmentRole.objects.get(
            assignment=swap_assignment,
            role_key="launch_coord",
        )

        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer_id == offer.id
        assert offer.status == "accepted"

        assert original_row.member_id == offerer.id
        assert swap_row.member_id == requester.id
        assert original_assignment.tow_pilot_id == offerer.id
        assert swap_assignment.tow_pilot_id == requester.id

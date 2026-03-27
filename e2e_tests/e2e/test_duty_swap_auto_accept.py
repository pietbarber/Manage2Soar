"""Focused E2E coverage for duty swap offer behavior (Issue #810).

Validates that:
- Cover offers are auto-accepted immediately from the Make Offer UI.
- Swap offers remain pending and require requester acceptance.
"""

from datetime import date, timedelta

from django.urls import reverse

from duty_roster.models import DutyAssignment, DutySwapOffer, DutySwapRequest
from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from siteconfig.models import SiteConfiguration


class TestDutySwapAutoAccept(DjangoPlaywrightTestCase):
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

    def _create_open_tow_swap_request(self):
        requester = self.create_test_member(
            username="swaprequester",
            email="swaprequester@example.com",
            membership_status="Full Member",
            towpilot=True,
        )
        offerer = self.create_test_member(
            username="swapofferer",
            email="swapofferer@example.com",
            membership_status="Full Member",
            towpilot=True,
        )

        target_date = date.today() + timedelta(days=14)
        DutyAssignment.objects.create(date=target_date, tow_pilot=requester)

        swap_request = DutySwapRequest.objects.create(
            requester=requester,
            original_date=target_date,
            role="TOW",
            request_type="general",
            status="open",
            notes="Need coverage",
        )

        return requester, offerer, swap_request

    def test_cover_offer_auto_accepts_from_ui(self):
        """Submitting a cover offer auto-accepts and fulfills the request."""
        requester, offerer, swap_request = self._create_open_tow_swap_request()

        self.login(username=offerer.username)
        offer_url = reverse("duty_roster:make_swap_offer", args=[swap_request.pk])
        self.page.goto(f"{self.live_server_url}{offer_url}")
        self.page.wait_for_selector("text=Make an Offer")

        self.page.check('input[name="offer_type"][value="cover"]')
        self.page.fill('textarea[name="notes"]', "I can cover this duty")
        self.page.get_by_role("button", name="Send Offer").click()

        detail_url = f"{self.live_server_url}{reverse('duty_roster:swap_request_detail', args=[swap_request.pk])}"
        self.page.wait_for_url(detail_url)
        self.page.wait_for_selector("text=Resolved!")
        self.page.wait_for_selector("text=ACCEPTED")

        offer = DutySwapOffer.objects.get(swap_request=swap_request, offered_by=offerer)
        assignment = DutyAssignment.objects.get(date=swap_request.original_date)
        swap_request.refresh_from_db()

        assert offer.status == "accepted"
        assert swap_request.status == "fulfilled"
        assert swap_request.accepted_offer_id == offer.id
        assert assignment.tow_pilot_id == offerer.id

    def test_swap_offer_stays_pending_until_requester_accepts(self):
        """Submitting a swap offer keeps the request open and offer pending."""
        requester, offerer, swap_request = self._create_open_tow_swap_request()
        proposed_date = date.today() + timedelta(days=21)

        self.login(username=offerer.username)
        offer_url = reverse("duty_roster:make_swap_offer", args=[swap_request.pk])
        self.page.goto(f"{self.live_server_url}{offer_url}")
        self.page.wait_for_selector("text=Make an Offer")

        self.page.check('input[name="offer_type"][value="swap"]')
        self.page.wait_for_function(
            "() => getComputedStyle(document.querySelector('#swap-date-section')).display !== 'none'"
        )
        self.page.fill('input[name="proposed_swap_date"]', proposed_date.isoformat())
        self.page.fill('textarea[name="notes"]', "Can trade with my duty date")
        self.page.get_by_role("button", name="Send Offer").click()

        detail_url = f"{self.live_server_url}{reverse('duty_roster:swap_request_detail', args=[swap_request.pk])}"
        self.page.wait_for_url(detail_url)
        self.page.wait_for_selector("text=Swap: Will take")

        offer = DutySwapOffer.objects.get(swap_request=swap_request, offered_by=offerer)
        swap_request.refresh_from_db()

        assert offer.status == "pending"
        assert swap_request.status == "open"
        assert swap_request.accepted_offer is None

        # Requester still sees manual Accept action for pending swap offers.
        self.context.clear_cookies()
        self.login(username=requester.username)
        self.page.goto(detail_url)
        self.page.wait_for_selector('button:has-text("Accept")')

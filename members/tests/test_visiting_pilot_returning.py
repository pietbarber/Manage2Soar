"""
Tests for the visiting-pilot "returning visitor" flow (Issue #1017).

Covers the landing page, the email-based lookup step, and the confirm/update
check-in step, including the yearly visit cap and the rule that an already
active member's membership_status is never downgraded.
"""

from django.test import Client, TestCase
from django.urls import reverse

from members.models import Member, VisitingPilotVisit
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.models import MembershipStatus, SiteConfiguration


class VisitingPilotReturningFlowTests(TestCase):
    TOKEN = "test-tok-returning"

    def setUp(self):
        self.client = Client()

        MembershipStatus.objects.get_or_create(
            name="Affiliate Member", defaults={"is_active": True, "sort_order": 90}
        )
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True, "sort_order": 10}
        )
        MembershipStatus.objects.get_or_create(
            name="Non-Member", defaults={"is_active": False, "sort_order": 200}
        )
        clear_active_membership_statuses_cache()

        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="testclub.com",
            club_abbreviation="TSC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
            visiting_pilot_auto_approve=True,
            visiting_pilot_token=self.TOKEN,
        )
        self.landing_url = reverse("members:visiting_pilot_landing", args=[self.TOKEN])
        self.lookup_url = reverse(
            "members:visiting_pilot_returning_lookup", args=[self.TOKEN]
        )
        self.confirm_url = reverse(
            "members:visiting_pilot_returning_confirm", args=[self.TOKEN]
        )

    def _lookup(self, email):
        return self.client.post(self.lookup_url, {"email": email})

    def test_landing_page_offers_both_choices(self):
        response = self.client.get(self.landing_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "flown here before")

    def test_lookup_no_match_redirects_to_first_time_signup(self):
        response = self._lookup("nobody@example.com")
        self.assertRedirects(
            response, reverse("members:visiting_pilot_signup", args=[self.TOKEN])
        )

    def test_lookup_ambiguous_match_shows_warning_without_session(self):
        Member.objects.create_user(
            username="dup1", email="dup@example.com", first_name="A", last_name="One"
        )
        Member.objects.create_user(
            username="dup2", email="dup@example.com", first_name="B", last_name="Two"
        )
        response = self._lookup("dup@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("visiting_pilot_candidate_id", self.client.session)

    def test_lookup_single_match_stores_session_and_redirects_to_confirm(self):
        Member.objects.create_user(
            username="paul", email="paul@example.com", first_name="Paul", last_name="P"
        )
        response = self._lookup("paul@example.com")
        self.assertRedirects(response, self.confirm_url)
        self.assertEqual(
            self.client.session["visiting_pilot_candidate_id"],
            Member.objects.get(email="paul@example.com").pk,
        )

    def test_lookup_blocks_already_active_member(self):
        """An anonymous visitor must never reach the edit page for an already-active member."""
        Member.objects.create_user(
            username="robert",
            email="robert@example.com",
            first_name="Robert",
            last_name="Anderson",
            membership_status="Full Member",
            is_active=True,
        )
        response = self._lookup("robert@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "existing active club member")
        self.assertNotIn("visiting_pilot_candidate_id", self.client.session)

    def test_confirm_blocks_active_member_even_with_forged_session(self):
        """Defense in depth: confirm view re-checks status even if session is set."""
        member = Member.objects.create_user(
            username="robert",
            email="robert@example.com",
            first_name="Robert",
            last_name="Anderson",
            membership_status="Full Member",
            is_active=True,
        )
        session = self.client.session
        session["visiting_pilot_candidate_id"] = member.pk
        session["visiting_pilot_candidate_token"] = self.TOKEN
        session.save()

        response = self.client.get(self.confirm_url)
        self.assertRedirects(response, self.lookup_url)
        self.assertNotIn("visiting_pilot_candidate_id", self.client.session)

        member.refresh_from_db()
        self.assertEqual(member.first_name, "Robert")  # untouched

    def test_confirm_without_lookup_redirects_to_lookup(self):
        response = self.client.get(self.confirm_url)
        self.assertRedirects(response, self.lookup_url)

    def test_confirm_upgrades_inactive_member_status(self):
        member = Member.objects.create_user(
            username="paul",
            email="paul@example.com",
            first_name="Paul",
            last_name="P",
            membership_status="Non-Member",
            is_active=False,
        )
        self._lookup("paul@example.com")

        response = self.client.post(
            self.confirm_url,
            {
                "phone": "555-1234",
                "home_club": "Northern Club",
            },
        )
        self.assertEqual(response.status_code, 200)

        member.refresh_from_db()
        self.assertEqual(member.membership_status, "Affiliate Member")
        self.assertTrue(member.is_active)
        self.assertEqual(member.phone, "555-1234")
        self.assertEqual(VisitingPilotVisit.visits_this_year(member), 1)

    def test_confirm_never_downgrades_already_active_member(self):
        member = Member.objects.create_user(
            username="paul",
            email="paul@example.com",
            first_name="Paul",
            last_name="P",
            membership_status="Full Member",
            is_active=True,
        )
        self._lookup("paul@example.com")

        self.client.post(self.confirm_url, {"home_club": "Northern Club"})

        member.refresh_from_db()
        self.assertEqual(member.membership_status, "Full Member")

    def test_confirm_clears_session_after_success(self):
        Member.objects.create_user(
            username="paul", email="paul@example.com", first_name="Paul", last_name="P"
        )
        self._lookup("paul@example.com")
        self.client.post(self.confirm_url, {})
        self.assertNotIn("visiting_pilot_candidate_id", self.client.session)

    def test_confirm_blocks_when_yearly_visit_cap_reached(self):
        self.config.visiting_pilot_max_visits_per_year = 1
        self.config.save()

        member = Member.objects.create_user(
            username="paul",
            email="paul@example.com",
            first_name="Paul",
            last_name="P",
            membership_status="Non-Member",
            is_active=False,
        )
        VisitingPilotVisit.objects.create(member=member)

        self._lookup("paul@example.com")
        response = self.client.post(self.confirm_url, {})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "reached the maximum")
        member.refresh_from_db()
        # Status must remain unchanged - the check-in was blocked.
        self.assertEqual(member.membership_status, "Non-Member")
        self.assertEqual(VisitingPilotVisit.visits_this_year(member), 1)


class VisitingPilotFirstTimeVisitLoggingTests(TestCase):
    """First-time signups should also be logged for the yearly visit cap."""

    TOKEN = "test-tok-firsttime"

    def setUp(self):
        self.client = Client()
        self.config = SiteConfiguration.objects.create(
            club_name="Test Soaring Club",
            domain_name="testclub.com",
            club_abbreviation="TSC",
            visiting_pilot_enabled=True,
            visiting_pilot_status="Affiliate Member",
            visiting_pilot_auto_approve=True,
            visiting_pilot_token=self.TOKEN,
            visiting_pilot_require_ssa=False,
            visiting_pilot_require_rating=False,
        )
        self.signup_url = reverse("members:visiting_pilot_signup", args=[self.TOKEN])

    def test_first_time_signup_creates_visit_record(self):
        self.client.post(
            self.signup_url,
            {
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane.doe@example.com",
                "phone": "",
                "ssa_member_number": "",
                "glider_rating": "",
            },
        )
        member = Member.objects.get(email="jane.doe@example.com")
        self.assertEqual(VisitingPilotVisit.visits_this_year(member), 1)

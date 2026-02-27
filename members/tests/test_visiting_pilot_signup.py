"""
Tests for the visiting pilot signup view (members.views.visiting_pilot_signup).

Verifies that the username assigned to newly created visiting pilot accounts
follows the ``firstname.lastname`` convention (issue #678) rather than using
the pilot's email address.
"""

from django.test import Client, TestCase
from django.urls import reverse

from members.models import Member
from siteconfig.models import SiteConfiguration


class VisitingPilotSignupUsernameTests(TestCase):
    """Visiting pilot signup creates accounts with firstname.lastname usernames."""

    TOKEN = "test-token-abc123"

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
            # Disable optional-field requirements so tests can use minimal form data.
            visiting_pilot_require_ssa=False,
            visiting_pilot_require_rating=False,
        )
        self.signup_url = reverse("members:visiting_pilot_signup", args=[self.TOKEN])

    def _post_signup(self, **overrides):
        data = {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane.doe@example.com",
            "phone": "",
            "ssa_member_number": "",
            "glider_rating": "",
        }
        data.update(overrides)
        return self.client.post(self.signup_url, data)

    def test_username_is_firstname_lastname_not_email(self):
        """Created account username is firstname.lastname, NOT the email address."""
        self._post_signup()

        member = Member.objects.get(email="jane.doe@example.com")
        self.assertEqual(
            member.username,
            "jane.doe",
            f"Expected username 'jane.doe', got {member.username!r}. "
            "Username should follow firstname.lastname convention (issue #678).",
        )
        # Explicit negative: must not be the email address
        self.assertNotEqual(
            member.username,
            "jane.doe@example.com",
            "Username must not be the email address.",
        )

    def test_username_strips_non_alpha_characters(self):
        """Hyphens and spaces in names are stripped from the username."""
        self._post_signup(first_name="Jean-Paul", last_name="Smith")

        member = Member.objects.get(email="jane.doe@example.com")
        self.assertEqual(member.username, "jeanpaul.smith")

    def test_email_stored_correctly(self):
        """Email field is still set to the actual email address."""
        self._post_signup()

        member = Member.objects.get(email="jane.doe@example.com")
        self.assertEqual(member.email, "jane.doe@example.com")

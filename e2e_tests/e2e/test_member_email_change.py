"""Browser coverage for the member email-change modal."""

from siteconfig.models import SiteConfiguration, default_member_profile_field_policies

from .conftest import DjangoPlaywrightTestCase


class TestMemberEmailChangeE2E(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()
        policies = default_member_profile_field_policies()
        policies["email"] = "direct"
        SiteConfiguration.objects.create(
            club_name="Test Club",
            domain_name="test.org",
            club_abbreviation="TC",
            member_profile_field_policies=policies,
        )
        self.member = self.create_test_member(
            username="email_browser",
            email="old@example.com",
        )

    def test_email_change_modal_submits_confirmation_request(self):
        self.login(username=self.member.username)
        self.page.goto(f"{self.live_server_url}/members/{self.member.pk}/view/")

        self.page.get_by_role("button", name="Change Email").click()
        self.page.locator("#emailSettingsModal").wait_for(state="visible")
        self.page.locator("#new_email").fill("new@example.com")
        self.page.get_by_role("button", name="Send Confirmation").click()

        self.page.wait_for_url(
            f"{self.live_server_url}/members/email/change/requested/"
        )
        assert "Check Your Email" in self.page.locator("body").inner_text()

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase


class TestMemberContactPrivacyReveal(DjangoPlaywrightTestCase):
    def test_staff_can_reveal_redacted_contact_by_click_and_keyboard(self):
        self.create_test_member(
            username="privacy_manager",
            member_manager=True,
        )
        subject = self.create_test_member(
            username="private_contact_member",
            email="private-contact@example.com",
            contact_visibility={"email": "hide"},
        )
        self.login(username="privacy_manager")

        self.page.goto(f"{self.live_server_url}/members/{subject.pk}/view/")
        reveal = (
            self.page.locator(".staff-reveal")
            .filter(has_text="private-contact@example.com")
            .first
        )
        redacted = reveal.locator(".staff-redacted")
        revealed = reveal.locator(".staff-revealed")

        assert redacted.is_visible()
        assert not revealed.is_visible()

        self.page.get_by_role("button", name="Dismiss").click()
        self.page.locator("#redaction-alert-modal").wait_for(state="hidden")

        reveal.click()
        assert revealed.is_visible()
        assert not redacted.is_visible()

        reveal.focus()
        self.page.keyboard.press("Enter")
        assert redacted.is_visible()
        self.page.keyboard.press("Space")
        assert revealed.is_visible()

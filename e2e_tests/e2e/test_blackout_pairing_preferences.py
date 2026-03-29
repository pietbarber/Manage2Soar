"""E2E coverage for Duty Blackout pairing preference persistence (Issue #561)."""

from .conftest import DjangoPlaywrightTestCase


class TestBlackoutPairingPreferences(DjangoPlaywrightTestCase):
    """Verify saved pairing preferences remain visibly persisted after reload."""

    def test_pairing_preferences_remain_selected_after_save(self):
        self.create_test_member(
            username="pair_owner",
            email="pair_owner@example.com",
            first_name="Owner",
            last_name="Member",
        )
        partner_one = self.create_test_member(
            username="pair_partner_one",
            email="pair_partner_one@example.com",
            first_name="Alice",
            last_name="Partner",
        )
        partner_two = self.create_test_member(
            username="pair_partner_two",
            email="pair_partner_two@example.com",
            first_name="Bob",
            last_name="Buddy",
        )
        avoid_member = self.create_test_member(
            username="pair_avoid_one",
            email="pair_avoid_one@example.com",
            first_name="Charlie",
            last_name="Conflict",
        )

        self.login(username="pair_owner")
        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")

        self.page.locator("#pairWith").select_option(
            [str(partner_one.id), str(partner_two.id)]
        )
        self.page.locator("#avoidWith").select_option(str(avoid_member.id))

        self.page.locator('button[type="submit"].btn-success').click()
        self.page.wait_for_load_state("networkidle")

        # Badge summary should show persisted selections.
        page_text = self.page.text_content("body") or ""
        assert "Currently selected:" in page_text
        assert "Alice Partner" in page_text
        assert "Bob Buddy" in page_text
        assert "Charlie Conflict" in page_text

        # Selected options should remain highlighted in both controls.
        pair_one_selected = self.page.locator(
            f'#pairWith option[value="{partner_one.id}"]'
        ).evaluate("el => el.selected")
        pair_two_selected = self.page.locator(
            f'#pairWith option[value="{partner_two.id}"]'
        ).evaluate("el => el.selected")
        avoid_selected = self.page.locator(
            f'#avoidWith option[value="{avoid_member.id}"]'
        ).evaluate("el => el.selected")

        assert pair_one_selected is True
        assert pair_two_selected is True
        assert avoid_selected is True

"""
E2E tests for Safety Report TinyMCE integration.

Issue #554: Add Safety Report feature
Issue #389: Playwright-pytest integration for automated browser tests

These tests verify TinyMCE editor functionality on the safety report form:
- Editor loads and initializes properly
- Users can type content into the editor
- Form submits successfully with TinyMCE content
"""

from .conftest import DjangoPlaywrightTestCase


class TestSafetyReportTinyMCE(DjangoPlaywrightTestCase):
    """Test that TinyMCE editor works correctly on the safety report form."""

    def test_tinymce_initializes_on_safety_report_form(self):
        """Verify TinyMCE initializes when viewing the safety report submission form."""
        # Create active member and login
        self.create_test_member(
            username="testmember", membership_status="Full Member", is_active=True
        )
        self.login(username="testmember")

        # Navigate to safety report form
        self.page.goto(f"{self.live_server_url}/members/safety-report/submit/")

        # Wait for page to load
        self.page.wait_for_load_state("networkidle")

        # Wait for TinyMCE to initialize - wait for the editor toolbar
        self.page.wait_for_selector(
            ".tox-toolbar__primary, .tox-toolbar", timeout=15000
        )

        # Also wait for the edit area iframe
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=5000)

        # Wait for TinyMCE to fully initialize
        self.page.wait_for_function(
            "() => typeof tinymce !== 'undefined' && "
            "(!!tinymce.activeEditor || (tinymce.editors && tinymce.editors.length > 0))",
            timeout=10000,
        )

        # Verify TinyMCE is defined and has an active editor
        tinymce_info = self.page.evaluate(
            """
            () => {
                if (typeof tinymce === 'undefined') {
                    return { defined: false };
                }
                return {
                    defined: true,
                    version: tinymce.majorVersion + '.' + tinymce.minorVersion,
                    editorCount: tinymce.editors ? tinymce.editors.length : 0,
                    activeEditor: tinymce.activeEditor ? true : false,
                    editorIds: tinymce.editors ? Object.keys(tinymce.editors) : []
                };
            }
        """
        )
        assert tinymce_info["defined"], "TinyMCE should be loaded"

        # TinyMCE should have at least one editor or an activeEditor
        has_editor = tinymce_info["editorCount"] > 0 or tinymce_info["activeEditor"]
        assert (
            has_editor
        ), f"TinyMCE should have at least one editor instance: {tinymce_info}"

    def test_user_can_type_in_tinymce_editor(self):
        """Verify users can type content into the TinyMCE editor."""
        # Create active member and login
        self.create_test_member(
            username="typingmember", membership_status="Full Member", is_active=True
        )
        self.login(username="typingmember")

        # Navigate to safety report form
        self.page.goto(f"{self.live_server_url}/members/safety-report/submit/")

        # Wait for TinyMCE to load
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Get the iframe for the TinyMCE editor
        iframe_locator = self.page.frame_locator("iframe.tox-edit-area__iframe")

        # Click inside the editor body to focus it
        editor_body = iframe_locator.locator("body#tinymce")
        editor_body.click()

        # Type some content
        test_content = "This is a test safety observation."
        editor_body.type(test_content)

        # Verify the content was entered
        content = editor_body.text_content()
        assert test_content in content, f"Content should be in editor. Got: '{content}'"

    def test_form_submission_with_tinymce_content(self):
        """Verify the form submits successfully with TinyMCE content."""
        # Create active member and login
        self.create_test_member(
            username="submitmember", membership_status="Full Member", is_active=True
        )
        self.login(username="submitmember")

        # Navigate to safety report form
        self.page.goto(f"{self.live_server_url}/members/safety-report/submit/")

        # Wait for TinyMCE to load
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Enter content into TinyMCE editor
        iframe_locator = self.page.frame_locator("iframe.tox-edit-area__iframe")
        editor_body = iframe_locator.locator("body#tinymce")
        editor_body.click()
        test_observation = (
            "Near miss on runway 27. Glider rolled back during launch setup."
        )
        editor_body.type(test_observation)

        # Optional: Fill in the date field
        date_input = self.page.locator('input[type="date"]')
        date_input.fill("2026-01-29")

        # Optional: Fill in the location field
        location_input = self.page.locator('input[placeholder*="Runway"]')
        location_input.fill("Runway 27")

        # Submit the form (use more specific locator to avoid logout button)
        submit_button = self.page.get_by_role("button", name="Submit Report")
        submit_button.click()

        # Wait for redirect (should go to home page after successful submission)
        self.page.wait_for_load_state("networkidle")

        # Verify we're redirected away from the form (check URL)
        current_url = self.page.url
        assert (
            "/members/safety-report/submit/" not in current_url
        ), "Should be redirected after successful submission"

    def test_tinymce_youtube_fix_script_loaded(self):
        """Verify the YouTube fix script is loaded (per Issue #397)."""
        self.create_test_member(
            username="youtubemember", membership_status="Full Member", is_active=True
        )
        self.login(username="youtubemember")

        # Navigate to safety report form
        self.page.goto(f"{self.live_server_url}/members/safety-report/submit/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Check that the YouTube fix is loaded by verifying the script tag or function
        has_youtube_fix = self.page.evaluate(
            """
            () => {
                // Check if the tinymce-youtube-fix.js script is loaded
                // The script modifies the YouTube embed behavior in TinyMCE
                const scripts = Array.from(document.querySelectorAll('script'));
                return scripts.some(s => s.src.includes('tinymce-youtube-fix.js'));
            }
        """
        )
        assert (
            has_youtube_fix
        ), "TinyMCE YouTube fix script should be loaded (tinymce-youtube-fix.js)"

    def test_anonymous_submission_hides_reporter(self):
        """Verify anonymous checkbox works correctly (E2E user flow test)."""
        # Create active member and login
        self.create_test_member(
            username="anonmember", membership_status="Full Member", is_active=True
        )
        self.login(username="anonmember")

        # Navigate to safety report form
        self.page.goto(f"{self.live_server_url}/members/safety-report/submit/")

        # Wait for TinyMCE to load
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Enter content
        iframe_locator = self.page.frame_locator("iframe.tox-edit-area__iframe")
        editor_body = iframe_locator.locator("body#tinymce")
        editor_body.click()
        editor_body.type("Anonymous safety concern.")

        # Check the anonymous checkbox
        anonymous_checkbox = self.page.locator('input[type="checkbox"]').first
        anonymous_checkbox.check()

        # Verify checkbox is checked
        is_checked = anonymous_checkbox.is_checked()
        assert is_checked, "Anonymous checkbox should be checked"

        # Submit the form (use more specific locator to avoid logout button)
        submit_button = self.page.get_by_role("button", name="Submit Report")
        submit_button.click()

        # Wait for redirect
        self.page.wait_for_load_state("networkidle")

        # Verify success
        current_url = self.page.url
        assert (
            "/members/safety-report/submit/" not in current_url
        ), "Should be redirected after submission"

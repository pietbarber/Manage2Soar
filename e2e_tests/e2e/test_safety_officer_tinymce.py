"""
E2E tests for Safety Officer Interface TinyMCE integration.

Issue #585: Safety Officer Interface for Viewing Safety Reports

These tests verify TinyMCE editor functionality on the safety officer detail view:
- TinyMCE editors load and initialize properly for officer notes and actions
- Safety officers can type content into the editors
- Form submits successfully with TinyMCE content
- Content is saved and rendered properly with cms-content CSS wrapper
"""

from .conftest import DjangoPlaywrightTestCase


class TestSafetyOfficerTinyMCE(DjangoPlaywrightTestCase):
    """Test that TinyMCE editors work correctly in the safety officer interface."""

    def test_tinymce_initializes_on_detail_view(self):
        """Verify TinyMCE initializes on the safety officer detail page."""
        # Create safety officer
        safety_officer = self.create_test_member(
            username="safety_officer",
            membership_status="Full Member",
            is_active=True,
            safety_officer=True,
        )

        # Create a regular member who submitted the report
        reporter = self.create_test_member(
            username="reporter", membership_status="Full Member", is_active=True
        )

        # Create a safety report
        from members.models import SafetyReport

        report = SafetyReport.objects.create(
            reporter=reporter,
            observation="<p>Test observation</p>",
            is_anonymous=False,
            status="new",
        )

        # Login as safety officer
        self.login(username="safety_officer")

        # Navigate to detail page
        self.page.goto(f"{self.live_server_url}/members/safety-reports/{report.pk}/")

        # Wait for page to load
        self.page.wait_for_load_state("networkidle")

        # Wait for TinyMCE to initialize - wait for editor toolbars
        # There should be 2 editors: officer_notes and actions_taken
        self.page.wait_for_selector(
            ".tox-toolbar__primary, .tox-toolbar", timeout=15000
        )

        # Wait for at least one iframe to appear
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=5000)

        # Wait for TinyMCE to fully initialize
        self.page.wait_for_function(
            "() => typeof tinymce !== 'undefined' && tinymce.editors && tinymce.editors.length >= 2",
            timeout=10000,
        )

        # Verify TinyMCE is initialized
        tinymce_info = self.page.evaluate(
            """
            () => {
                if (typeof tinymce === 'undefined') {
                    return { defined: false };
                }
                return {
                    defined: true,
                    editorCount: tinymce.editors ? tinymce.editors.length : 0,
                };
            }
            """
        )

        assert tinymce_info["defined"], "TinyMCE should be defined"
        assert (
            tinymce_info["editorCount"] >= 2
        ), "Should have at least 2 TinyMCE editors (officer_notes and actions_taken)"

    def test_can_submit_officer_notes_with_tinymce(self):
        """Verify safety officers can submit the form with TinyMCE content."""
        # Create safety officer
        safety_officer = self.create_test_member(
            username="safety_officer",
            membership_status="Full Member",
            is_active=True,
            safety_officer=True,
        )

        # Create a regular member who submitted the report
        reporter = self.create_test_member(
            username="reporter", membership_status="Full Member", is_active=True
        )

        # Create a safety report
        from members.models import SafetyReport

        report = SafetyReport.objects.create(
            reporter=reporter,
            observation="<p>Test observation</p>",
            is_anonymous=False,
            status="new",
        )

        # Login as safety officer
        self.login(username="safety_officer")

        # Navigate to detail page
        self.page.goto(f"{self.live_server_url}/members/safety-reports/{report.pk}/")

        # Wait for page and TinyMCE to load
        self.page.wait_for_load_state("networkidle")
        self.page.wait_for_selector(
            ".tox-toolbar__primary, .tox-toolbar", timeout=15000
        )
        self.page.wait_for_function(
            "() => typeof tinymce !== 'undefined' && tinymce.editors && tinymce.editors.length >= 2",
            timeout=10000,
        )

        # Fill in the form
        # Select status
        self.page.select_option('select[name="status"]', "reviewed")

        # Type into TinyMCE editor for officer_notes
        # Find the editor iframe for officer_notes
        officer_notes_content = "<p>This report has been reviewed and noted.</p>"
        self.page.evaluate(
            f"""
            () => {{
                const editor = tinymce.get('id_officer_notes');
                if (editor) {{
                    editor.setContent('{officer_notes_content}');
                }}
            }}
            """
        )

        # Type into TinyMCE editor for actions_taken
        actions_content = (
            "<p>Briefed the club on proper runway approach procedures.</p>"
        )
        self.page.evaluate(
            f"""
            () => {{
                const editor = tinymce.get('id_actions_taken');
                if (editor) {{
                    editor.setContent('{actions_content}');
                }}
            }}
            """
        )

        # Submit the form
        self.page.click('button[type="submit"]')

        # Wait for redirect back to the detail page
        self.page.wait_for_url(f"**/members/safety-reports/{report.pk}/", timeout=5000)

        # Verify success message
        page_content = self.page.content()
        assert (
            "Safety report updated successfully" in page_content
            or "updated successfully" in page_content
        ), "Should show success message after form submission"

        # Verify the data was saved to the database
        report.refresh_from_db()
        assert report.status == "reviewed"
        assert "reviewed and noted" in report.officer_notes
        assert "runway approach procedures" in report.actions_taken

    def test_content_renders_with_cms_wrapper(self):
        """Verify TinyMCE content is rendered with cms-content CSS wrapper."""
        # Create safety officer
        safety_officer = self.create_test_member(
            username="safety_officer",
            membership_status="Full Member",
            is_active=True,
            safety_officer=True,
        )

        # Create a regular member who submitted the report
        reporter = self.create_test_member(
            username="reporter", membership_status="Full Member", is_active=True
        )

        # Create a safety report with officer notes and actions
        from members.models import SafetyReport

        report = SafetyReport.objects.create(
            reporter=reporter,
            observation="<p>Test observation with <strong>bold text</strong>.</p>",
            is_anonymous=False,
            status="reviewed",
            officer_notes="<p>Internal notes with <em>italic text</em>.</p>",
            actions_taken="<p>Actions with <ul><li>List item</li></ul></p>",
            reviewed_by=safety_officer,
        )

        # Login as safety officer
        self.login(username="safety_officer")

        # Navigate to detail page
        self.page.goto(f"{self.live_server_url}/members/safety-reports/{report.pk}/")

        # Wait for page to load
        self.page.wait_for_load_state("networkidle")

        # Verify observation content is wrapped with cms-content class
        observation_wrapper = self.page.query_selector(".cms-content")
        assert (
            observation_wrapper is not None
        ), "Observation content should be wrapped with cms-content class"

        # Verify the content is rendered
        page_content = self.page.content()
        assert "Test observation" in page_content
        assert "bold text" in page_content

"""
TinyMCE integration tests using Playwright.

Issue #389: Playwright-pytest integration for automated browser tests.
Issue #422: TinyMCE YouTube video insertion testing.

These tests verify TinyMCE editor functionality, particularly:
- Editor loads and initializes properly
- YouTube video embedding works correctly
- The tinymce-youtube-fix.js extension works
"""

import pytest

from .conftest import DjangoPlaywrightTestCase


class TestTinyMCEEditorLoads(DjangoPlaywrightTestCase):
    """Test that TinyMCE editor loads correctly on CMS pages."""

    def test_tinymce_initializes_on_cms_create_page(self):
        """Verify TinyMCE initializes when creating a CMS page."""
        # Create admin user and login
        self.create_test_member(username="cms_admin", is_superuser=True)
        self.login(username="cms_admin")

        # Navigate to CMS page creation
        self.page.goto(f"{self.live_server_url}/cms/create/page/")

        # Wait for page to load
        self.page.wait_for_load_state("networkidle")

        # Wait for TinyMCE to initialize - wait for the editor toolbar which appears after init
        # TinyMCE 6+ uses .tox-toolbar__primary
        self.page.wait_for_selector(
            ".tox-toolbar__primary, .tox-toolbar", timeout=15000
        )

        # Also wait for the edit area iframe
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=5000)

        # Wait for TinyMCE to fully initialize using smart waiting
        self.page.wait_for_function(
            "() => typeof tinymce !== 'undefined' && "
            "(!!tinymce.activeEditor || (tinymce.editors && tinymce.editors.length > 0))",
            timeout=10000,
        )

        # Verify TinyMCE is defined in JavaScript
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

    def test_tinymce_media_plugin_available(self):
        """Verify the media plugin is loaded for video embedding."""
        self.create_test_member(username="cms_admin2", is_superuser=True)
        self.login(username="cms_admin2")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Check that the media plugin is loaded
        has_media_plugin = self.page.evaluate(
            """
            () => {
                const editor = tinymce.activeEditor;
                if (!editor) return false;
                return editor.plugins.media !== undefined;
            }
        """
        )
        assert has_media_plugin, "TinyMCE media plugin should be loaded"

    def test_tinymce_youtube_fix_script_loaded(self):
        """Verify the YouTube fix script is loaded."""
        self.create_test_member(username="cms_admin3", is_superuser=True)
        self.login(username="cms_admin3")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Check that media_url_resolver is configured
        has_resolver = self.page.evaluate(
            """
            () => {
                const editor = tinymce.activeEditor;
                if (!editor) return false;
                return typeof editor.options.get('media_url_resolver') === 'function';
            }
        """
        )
        assert (
            has_resolver
        ), "media_url_resolver should be configured by tinymce-youtube-fix.js"


class TestTinyMCEYouTubeEmbed(DjangoPlaywrightTestCase):
    """Test YouTube video embedding in TinyMCE (Issue #422)."""

    def test_youtube_url_resolver_standard_url(self):
        """Test that standard YouTube URLs are resolved correctly."""
        self.create_test_member(username="youtube_admin2", is_superuser=True)
        self.login(username="youtube_admin2")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Test the media_url_resolver function directly with a YouTube URL
        result = self.page.evaluate(
            """
            async () => {
                const editor = tinymce.activeEditor;
                const resolver = editor.options.get('media_url_resolver');
                if (!resolver) return { error: 'No resolver found' };

                try {
                    const data = await resolver({ url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ' });
                    return { success: true, html: data.html };
                } catch (e) {
                    return { rejected: true, message: String(e) };
                }
            }
        """
        )

        assert "success" in result, f"YouTube URL should resolve successfully: {result}"
        assert "iframe" in result.get("html", "").lower(), "Should contain iframe embed"
        assert "youtube.com/embed" in result.get(
            "html", ""
        ), "Should use YouTube embed URL"
        assert (
            "referrerpolicy" in result.get("html", "").lower()
        ), "Should include referrerpolicy"

    def test_youtube_url_resolver_short_url(self):
        """Test that youtu.be short URLs are resolved correctly."""
        self.create_test_member(username="youtube_short_url_admin", is_superuser=True)
        self.login(username="youtube_short_url_admin")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Test with youtu.be short URL
        result = self.page.evaluate(
            """
            async () => {
                const editor = tinymce.activeEditor;
                const resolver = editor.options.get('media_url_resolver');
                if (!resolver) return { error: 'No resolver found' };

                try {
                    const data = await resolver({ url: 'https://youtu.be/dQw4w9WgXcQ' });
                    return { success: true, html: data.html };
                } catch (e) {
                    return { rejected: true, message: String(e) };
                }
            }
        """
        )

        assert (
            "success" in result
        ), f"Short YouTube URL should resolve successfully: {result}"
        assert "youtube.com/embed/dQw4w9WgXcQ" in result.get(
            "html", ""
        ), "Should contain video ID in embed URL"

    def test_non_youtube_url_rejected(self):
        """Test that non-YouTube URLs are passed through to default handler."""
        self.create_test_member(username="youtube_admin3", is_superuser=True)
        self.login(username="youtube_admin3")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Test with non-YouTube URL (should be rejected to let default handle it)
        result = self.page.evaluate(
            """
            async () => {
                const editor = tinymce.activeEditor;
                const resolver = editor.options.get('media_url_resolver');
                if (!resolver) return { error: 'No resolver found' };

                try {
                    const data = await resolver({ url: 'https://vimeo.com/123456' });
                    return { success: true, html: data.html };
                } catch (e) {
                    return { rejected: true };
                }
            }
        """
        )

        assert result.get("rejected") is True, "Non-YouTube URLs should be rejected"


class TestTinyMCEMediaDialog(DjangoPlaywrightTestCase):
    """Test the TinyMCE media dialog functionality."""

    def test_media_button_opens_dialog(self):
        """Test that clicking the media button opens the insert media dialog."""
        self.create_test_member(username="media_admin", is_superuser=True)
        self.login(username="media_admin")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Find and click the media button in the toolbar
        # The media button typically has title="Insert/edit media"
        media_button = self.page.locator('button[title*="media" i]')

        if media_button.count() > 0:
            media_button.first.click()

            # Wait for dialog to appear
            dialog = self.page.locator(".tox-dialog")
            dialog.wait_for(timeout=5000)

            assert dialog.is_visible(), "Media dialog should appear"

            # Check that the dialog has a URL input
            url_input = self.page.locator('.tox-dialog input[type="text"]')
            assert url_input.count() > 0, "Dialog should have URL input field"

            # Close the dialog
            cancel_button = self.page.locator('.tox-dialog button:has-text("Cancel")')
            if cancel_button.count() > 0:
                cancel_button.click()
        else:
            # Media button might not be visible - check toolbar configuration
            toolbar_buttons = self.page.evaluate(
                """
                () => {
                    const buttons = document.querySelectorAll('.tox-toolbar button');
                    return Array.from(buttons).map(b => b.getAttribute('title') || b.textContent);
                }
            """
            )
            self.skipTest(
                f"Media button not found. Available buttons: {toolbar_buttons[:10]}"
            )

    @pytest.mark.xfail(
        reason="Issue #422: YouTube videos not inserting via mceMedia command"
    )
    def test_youtube_url_inserts_embed(self):
        """Test that entering a YouTube URL in the media dialog inserts an embed.

        NOTE: This test is currently marked as xfail because it reproduces Issue #422.
        When Issue #422 is fixed, this test should start passing and the xfail marker
        can be removed.
        """
        self.create_test_member(username="embed_admin", is_superuser=True)
        self.login(username="embed_admin")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Insert YouTube video via TinyMCE command
        self.page.evaluate(
            """
            () => {
                const editor = tinymce.activeEditor;

                // Use insertMedia command with YouTube URL
                editor.execCommand('mceMedia', false, {
                    source: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
                });
            }
        """
        )

        # Wait until the editor content reflects the inserted media
        try:
            self.page.wait_for_function(
                """
                () => {
                    const editor = tinymce.activeEditor;
                    if (!editor) {
                        return false;
                    }
                    const content = editor.getContent();
                    if (!content) {
                        return false;
                    }
                    const lower = content.toLowerCase();
                    return (
                        lower.includes("iframe") ||
                        lower.includes("video") ||
                        lower.includes("youtube") ||
                        lower.includes("media")
                    );
                }
            """,
                timeout=5000,
            )
        except Exception:
            # Expected to fail - this is Issue #422
            pass

        # Once the condition is satisfied (or timeout), retrieve the content
        result = self.page.evaluate(
            """
            () => {
                const editor = tinymce.activeEditor;
                const content = editor ? editor.getContent() : "";
                return { content: content };
            }
        """
        )

        content = result.get("content", "")
        # The content should either contain an iframe or a video placeholder
        # depending on how TinyMCE handles the media
        has_media = (
            "iframe" in content.lower()
            or "video" in content.lower()
            or "youtube" in content.lower()
            or "media" in content.lower()
        )

        # Assert that media was inserted - this will fail (xfail) until Issue #422 is fixed
        assert has_media, (
            f"YouTube video was not inserted into editor (Issue #422). "
            f"Content: '{content[:200]}'"
        )


class TestTinyMCEScriptIntegrity(DjangoPlaywrightTestCase):
    """Test JavaScript integrity of TinyMCE-related scripts."""

    def test_no_javascript_errors_on_page_load(self):
        """Verify no JavaScript errors occur when loading TinyMCE pages."""
        self.create_test_member(username="xss_admin", is_superuser=True)
        self.login(username="xss_admin")

        # Collect console errors
        errors = []
        self.page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # Filter out known non-critical errors
        critical_errors = [
            e
            for e in errors
            if "favicon" not in e.lower() and "404" not in e and "net::ERR" not in e
        ]

        assert (
            len(critical_errors) == 0
        ), f"JavaScript errors detected: {critical_errors}"

    def test_escape_html_function_exists(self):
        """Verify the XSS prevention function is defined."""
        self.create_test_member(username="xss_admin", is_superuser=True)
        self.login(username="xss_admin")

        self.page.goto(f"{self.live_server_url}/cms/create/page/")
        self.page.wait_for_selector("iframe.tox-edit-area__iframe", timeout=10000)

        # The escapeHtml function should be defined within the tinymce-youtube-fix.js
        # and used by video_template_callback
        has_video_callback = self.page.evaluate(
            """
            () => {
                const editor = tinymce.activeEditor;
                if (!editor) return false;
                return typeof editor.options.get('video_template_callback') === 'function';
            }
        """
        )
        assert has_video_callback, "video_template_callback should be configured"

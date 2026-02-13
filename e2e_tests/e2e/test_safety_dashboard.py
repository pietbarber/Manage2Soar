"""
E2E tests for Safety Officer Dashboard (Issue #622).

Tests Bootstrap tab switching, independent pagination, and show/hide toggle.
"""

from datetime import date, timedelta

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase


class TestSafetyDashboardE2E(DjangoPlaywrightTestCase):
    """E2E tests for dashboard JavaScript interactions."""

    def test_tab_switching(self):
        """Test switching between Suggestion Box and Ops Safety tabs."""
        # Create safety officer
        safety_officer = self.create_test_member(
            username="safetyofficer",
            is_superuser=False,
            safety_officer=True,
        )
        self.login(username="safetyofficer")

        # Navigate to dashboard
        self.page.goto(f"{self.live_server_url}/members/safety-dashboard/")

        # Verify Suggestion Box tab is active by default
        suggestions_tab = self.page.locator("#suggestions-tab")
        assert "active" in suggestions_tab.get_attribute("class")

        # Verify Suggestion Box content is visible
        suggestions_content = self.page.locator("#suggestions")
        assert suggestions_content.is_visible()

        # Ops Safety content should not be visible
        ops_content = self.page.locator("#ops-safety")
        assert not ops_content.is_visible()

        # Click on Ops Safety tab
        ops_tab = self.page.locator("#ops-safety-tab")
        ops_tab.click()

        # Wait for tab transition
        self.page.wait_for_timeout(300)

        # Verify Ops Safety tab is now active
        assert "active" in ops_tab.get_attribute("class")

        # Verify Ops Safety content is now visible
        assert ops_content.is_visible()

        # Suggestion Box content should not be visible
        assert not suggestions_content.is_visible()

    def test_pagination_works(self):
        """Test that pagination displays correctly for ops safety entries."""
        from logsheet.models import Airfield, Logsheet, LogsheetCloseout
        from members.models import SafetyReport

        # Create safety officer
        safety_officer = self.create_test_member(
            username="safetyofficer",
            is_superuser=False,
            safety_officer=True,
        )

        # Create airfield
        airfield = Airfield.objects.create(name="Test Airfield", identifier="TST")

        # Create 15 ops safety entries (more than paginator's 10 per page)
        for i in range(15):
            logsheet = Logsheet.objects.create(
                log_date=date.today() - timedelta(days=i * 7),
                airfield=airfield,
                created_by=safety_officer,
                finalized=True,
            )
            LogsheetCloseout.objects.create(
                logsheet=logsheet,
                safety_issues=f"<p>Safety issue {i + 1}</p>",
            )

        self.login(username="safetyofficer")
        self.page.goto(f"{self.live_server_url}/members/safety-dashboard/")

        # Switch to Ops Safety tab
        ops_tab = self.page.locator("#ops-safety-tab")
        ops_tab.click()

        # Wait for the Ops Safety content to be visible
        ops_content = self.page.locator("#ops-safety")
        ops_content.wait_for(state="visible")

        # Verify pagination exists (should have 15 entries, 10 per page)
        pagination = ops_content.locator(".pagination")
        assert pagination.is_visible()

        # Verify we can see page 2 link
        page_2_link = ops_content.locator("a.page-link:has-text('2')")
        assert page_2_link.is_visible()

    def test_show_hide_filter_toggle(self):
        """Test the show/hide 'nothing to report' toggle button works correctly."""
        from logsheet.models import Airfield, Logsheet, LogsheetCloseout

        # Create safety officer
        safety_officer = self.create_test_member(
            username="safetyofficer",
            is_superuser=False,
            safety_officer=True,
        )

        # Create airfield
        airfield = Airfield.objects.create(name="Test Airfield", identifier="TST")

        # Create one substantive entry and one "nothing to report" entry
        logsheet1 = Logsheet.objects.create(
            log_date=date.today() - timedelta(days=7),
            airfield=airfield,
            created_by=safety_officer,
            finalized=True,
        )
        LogsheetCloseout.objects.create(
            logsheet=logsheet1,
            safety_issues="<p>Rope break on third tow</p>",
        )

        logsheet2 = Logsheet.objects.create(
            log_date=date.today() - timedelta(days=14),
            airfield=airfield,
            created_by=safety_officer,
            finalized=True,
        )
        LogsheetCloseout.objects.create(
            logsheet=logsheet2,
            safety_issues="<p>Nothing to report</p>",
        )

        self.login(username="safetyofficer")

        # Test default filtered view
        self.page.goto(f"{self.live_server_url}/members/safety-dashboard/")
        ops_tab = self.page.locator("#ops-safety-tab")
        ops_tab.click()
        ops_content = self.page.locator("#ops-safety")
        ops_content.wait_for(state="visible")

        # Should only see substantive entry by default
        assert "Rope break" in ops_content.text_content()
        assert "Nothing to report" not in ops_content.text_content()

        # Navigate to show all view
        self.page.goto(
            f"{self.live_server_url}/members/safety-dashboard/?show_all_ops=1"
        )
        ops_tab = self.page.locator("#ops-safety-tab")
        ops_tab.click()
        ops_content = self.page.locator("#ops-safety")
        ops_content.wait_for(state="visible")

        # Both entries should be visible
        content_text = ops_content.text_content()
        assert "Rope break" in content_text
        assert "Nothing to report" in content_text

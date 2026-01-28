"""
End-to-end tests for the maintenance log page JavaScript functionality.

Tests the dynamic aircraft filtering behavior to ensure JavaScript works correctly
as per coding guideline CG-1000000.
"""

import pytest

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Glider, MaintenanceIssue, Towplane


class TestMaintenanceLogE2E(DjangoPlaywrightTestCase):
    """E2E tests for maintenance log JavaScript functionality."""

    @pytest.mark.django_db
    def test_aircraft_filter_javascript_functionality(self):
        """Test that JavaScript filter dropdown works correctly."""
        # Create test user and data
        self.create_test_member(username="admin", is_superuser=True)

        # Create test aircraft
        glider = Glider.objects.create(
            n_number="N123AB", make="Schleicher", model="ASK21", is_active=True
        )
        towplane = Towplane.objects.create(
            name="Test Towplane",
            n_number="N456TP",
            make="Piper",
            model="Super Cub",
            is_active=True,
        )

        # Create maintenance issues for both aircraft
        MaintenanceIssue.objects.create(
            description="Glider brake issue", glider=glider, resolved=False
        )
        MaintenanceIssue.objects.create(
            description="Towplane engine issue", towplane=towplane, resolved=False
        )

        # Login and navigate to maintenance log
        self.login(username="admin")
        self.page.goto(f"{self.live_server_url}/logsheet/maintenance/log/")

        # Verify page loads and shows all issues initially
        self.page.wait_for_selector("table")
        rows = self.page.locator("tbody tr")
        assert rows.count() == 2

        # Verify content is displayed
        tbody_text = self.page.text_content("tbody") or ""
        assert "Glider brake issue" in tbody_text
        assert "Towplane engine issue" in tbody_text

        # Test that JavaScript populates the hidden type field
        self.page.select_option("#aircraft-select", str(glider.id))

        # Wait for JavaScript event to complete
        self.page.wait_for_timeout(100)

        # Check that JavaScript updated the type field
        type_field = self.page.locator("#type-field")
        assert type_field.get_attribute("value") == "glider"

        # Submit the form and verify filtered results
        self.page.click("button.btn-outline-primary")
        self.page.wait_for_load_state("networkidle")

        # Verify we're still on the maintenance log page
        assert "/logsheet/maintenance/log/" in self.page.url

        # Verify page reloaded with filtered results
        rows = self.page.locator("tbody tr")
        assert rows.count() == 1  # Only glider issue should be shown

        # Verify only glider issue is displayed
        tbody_text = self.page.text_content("tbody") or ""
        assert "Glider brake issue" in tbody_text
        assert "Towplane engine issue" not in tbody_text

        # Verify dropdown maintains the selected value after form submission
        selected_value = self.page.locator("#aircraft-select").input_value()
        assert selected_value == str(glider.id)

        # Test Clear button functionality
        self.page.click("a.btn-outline-secondary")
        self.page.wait_for_load_state("networkidle")

        # Verify all issues are shown again after clearing
        rows = self.page.locator("tbody tr")
        assert rows.count() == 2
        tbody_text = self.page.text_content("tbody") or ""
        assert "Glider brake issue" in tbody_text
        assert "Towplane engine issue" in tbody_text

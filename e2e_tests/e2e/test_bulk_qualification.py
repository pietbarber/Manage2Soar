"""
End-to-end tests for bulk qualification assignment (Issue #339).

Tests the full browser workflow including:
- Page rendering with member checklist
- JavaScript select/deselect functionality
- Form submission creating qualification records
- Permission enforcement
"""

import pytest
from django.test import tag

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from instructors.models import ClubQualificationType, MemberQualification
from siteconfig.models import MembershipStatus


@tag("e2e")
class TestBulkQualificationE2E(DjangoPlaywrightTestCase):
    """E2E tests for the bulk qualification assignment page."""

    def setUp(self):
        super().setUp()
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )
        self.qual = ClubQualificationType.objects.create(
            code="SM2026",
            name="Safety Meeting 2026",
            applies_to="both",
        )
        self.qual2 = ClubQualificationType.objects.create(
            code="CFI",
            name="Certified Flight Instructor",
            applies_to="rated",
        )
        # Create instructor who can access the page
        self.instructor = self.create_test_member(
            username="instructor",
            first_name="Test",
            last_name="Instructor",
            instructor=True,
        )
        # Create some regular members to appear in the checklist
        self.member1 = self.create_test_member(
            username="alice",
            first_name="Alice",
            last_name="Aaronson",
        )
        self.member2 = self.create_test_member(
            username="bob",
            first_name="Bob",
            last_name="Baker",
        )
        self.member3 = self.create_test_member(
            username="carol",
            first_name="Carol",
            last_name="Carter",
        )

    def test_page_loads_with_member_checklist(self):
        """Page loads and displays qualification form with member checkboxes."""
        self.login(username="instructor")
        self.page.goto(f"{self.live_server_url}/instructors/bulk-assign-qualification/")

        # Page title is visible
        h1_text = self.page.text_content("h1") or ""
        assert "Bulk Assign Qualification" in h1_text

        # Qualification dropdown is present
        qual_select = self.page.locator("#id_qualification")
        assert qual_select.is_visible()

        # Member checkboxes are present
        checkboxes = self.page.locator('.member-checklist input[type="checkbox"]')
        assert checkboxes.count() >= 3  # at least our 3 test members

    def test_select_all_button(self):
        """'Select All' button checks all visible member checkboxes."""
        self.login(username="instructor")
        self.page.goto(f"{self.live_server_url}/instructors/bulk-assign-qualification/")

        # Click Select All
        self.page.click("#select-all-btn")

        # All checkboxes should be checked
        checkboxes = self.page.locator('.member-checklist input[type="checkbox"]')
        count = checkboxes.count()
        checked = 0
        for i in range(count):
            if checkboxes.nth(i).is_checked():
                checked += 1
        assert checked == count
        badge_text = self.page.text_content("#selected-count-badge") or ""
        assert f"{count} selected" in badge_text

    def test_deselect_all_button(self):
        """'Deselect All' button unchecks all member checkboxes."""
        self.login(username="instructor")
        self.page.goto(f"{self.live_server_url}/instructors/bulk-assign-qualification/")

        # Select all first
        self.page.click("#select-all-btn")
        # Then deselect all
        self.page.click("#deselect-all-btn")

        checkboxes = self.page.locator('.member-checklist input[type="checkbox"]')
        for i in range(checkboxes.count()):
            assert not checkboxes.nth(i).is_checked()
        badge_text = self.page.text_content("#selected-count-badge") or ""
        assert "0 selected" in badge_text

    def test_search_filter(self):
        """Search box filters member list by name."""
        self.login(username="instructor")
        self.page.goto(f"{self.live_server_url}/instructors/bulk-assign-qualification/")

        # Type a search query
        self.page.fill("#member-search", "Alice")

        # Wait for filter to take effect by observing the filter-status text update
        self.page.wait_for_function(
            "document.querySelector('#filter-status') && "
            "document.querySelector('#filter-status').textContent.includes('Showing')"
        )

        # Only matching members should be visible
        visible_items = self.page.locator('.member-item:not([style*="display: none"])')
        assert visible_items.count() >= 1

        # Filter status should show
        filter_status = self.page.text_content("#filter-status") or ""
        assert "Showing" in filter_status

    def test_full_submission_workflow(self):
        """Complete workflow: select qualification, check members, submit."""
        self.login(username="instructor")
        self.page.goto(f"{self.live_server_url}/instructors/bulk-assign-qualification/")

        # Select a qualification
        self.page.select_option("#id_qualification", str(self.qual.pk))

        # Check specific members
        checkboxes = self.page.locator('.member-checklist input[type="checkbox"]')
        for i in range(min(2, checkboxes.count())):
            checkboxes.nth(i).check()

        # Submit the form
        self.page.click("#submit-btn")

        # Should redirect and show success message
        self.page.wait_for_url("**/bulk-assign-qualification/")
        success_alert = self.page.locator(".alert-success")
        assert success_alert.is_visible()
        alert_text = success_alert.text_content() or ""
        assert "Safety Meeting 2026" in alert_text

        # Verify records were created in the database
        assert MemberQualification.objects.filter(qualification=self.qual).count() >= 1

    def test_regular_member_sees_403(self):
        """Regular member without instructor/safety_officer flag gets 403."""
        regular = self.create_test_member(
            username="regular",
            first_name="Regular",
            last_name="User",
        )
        self.login(username="regular")
        self.page.goto(f"{self.live_server_url}/instructors/bulk-assign-qualification/")

        # Should see a 403 page
        page_content = self.page.content()
        assert "Access Denied" in page_content or "Permission Denied" in page_content

    def test_select_without_qual_button(self):
        """'Select Without Qual' button checks only members lacking the qualification."""
        # Give member1 the qualification already
        MemberQualification.objects.create(
            member=self.member1,
            qualification=self.qual,
            is_qualified=True,
            date_awarded="2026-01-01",
        )

        self.login(username="instructor")
        self.page.goto(f"{self.live_server_url}/instructors/bulk-assign-qualification/")

        # Select the qualification
        self.page.select_option("#id_qualification", str(self.qual.pk))
        # Wait for any badge/indicator updates triggered by qualification selection
        self.page.wait_for_load_state("networkidle")

        # Click "Select Without Qual"
        self.page.click("#select-without-qual-btn")
        # Wait for checkboxes to be updated by observing badge count change
        self.page.wait_for_function(
            "document.querySelector('#selected-count-badge') && "
            "!document.querySelector('#selected-count-badge').textContent.includes('0 selected')"
        )

        # The member who already has the qual should NOT be checked
        # Members without the qual should be checked
        checkboxes = self.page.locator('.member-checklist input[type="checkbox"]')
        checked_count = 0
        for i in range(checkboxes.count()):
            cb = checkboxes.nth(i)
            value = cb.get_attribute("value") or "0"
            member_id = int(value)
            if member_id == self.member1.pk:
                assert (
                    not cb.is_checked()
                ), "Member who already has qualification should not be checked"
            else:
                assert (
                    cb.is_checked()
                ), "Members without the qualification should be checked"
                checked_count += 1

        assert checked_count >= 2  # at least member2 and member3

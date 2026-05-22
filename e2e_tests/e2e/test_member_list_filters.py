"""E2E coverage for member list filter UI interactions.

Validates browser behavior for the accordion-based filter controls:
- accordion opens and exposes filter controls
- role checkbox interaction filters visible members
- Clear Statuses unchecks status filters and Apply Filters shows empty state
"""

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.models import MembershipStatus


class TestMemberListFilters(DjangoPlaywrightTestCase):
    def setUp(self):
        super().setUp()

        MembershipStatus.objects.get_or_create(
            name="Aero Member", defaults={"is_active": True, "sort_order": 10}
        )
        MembershipStatus.objects.get_or_create(
            name="Guest Pilot", defaults={"is_active": False, "sort_order": 20}
        )
        clear_active_membership_statuses_cache()

    def test_member_list_filter_accordion_role_and_clear_statuses_flow(self):
        self.create_test_member(
            username="memberviewer",
            first_name="View",
            last_name="User",
            membership_status="Aero Member",
        )
        self.create_test_member(
            username="manageractive",
            first_name="Manager",
            last_name="Active",
            membership_status="Aero Member",
            member_manager=True,
        )
        self.create_test_member(
            username="regularactive",
            first_name="Regular",
            last_name="Active",
            membership_status="Aero Member",
            member_manager=False,
        )
        self.create_test_member(
            username="guestinactive",
            first_name="Guest",
            last_name="Inactive",
            membership_status="Guest Pilot",
            member_manager=True,
        )

        self.login(username="memberviewer")
        self.page.goto(f"{self.live_server_url}/members/")

        # Default view: active members shown, inactive hidden.
        assert self.page.locator("text=Manager Active").first.is_visible()
        assert self.page.locator("text=Regular Active").first.is_visible()
        assert self.page.locator("text=Guest Inactive").count() == 0

        # Open accordion and apply role filter through the form.
        self.page.click('button[data-bs-target="#memberFiltersCollapse"]')
        self.page.wait_for_selector("#memberFiltersCollapse.show")
        self.page.check('input[name="role"][value="member_manager"]')
        self.page.click('#filterForm button[type="submit"]')
        self.page.wait_for_url(f"{self.live_server_url}/members/**")

        assert self.page.locator("text=Manager Active").first.is_visible()
        assert self.page.locator("text=Regular Active").count() == 0

        # Reset and verify clear-statuses + apply-filters browser behavior.
        self.page.goto(f"{self.live_server_url}/members/")
        self.page.click('button[data-bs-target="#memberFiltersCollapse"]')
        self.page.wait_for_selector("#memberFiltersCollapse.show")

        checked_before = self.page.locator('input[name="status"]:checked').count()
        assert checked_before > 0

        self.page.click("#clearStatusFilters")
        checked_after = self.page.locator('input[name="status"]:checked').count()
        assert checked_after == 0

        self.page.click('#filterForm button[type="submit"]')
        self.page.wait_for_url(f"{self.live_server_url}/members/**")
        assert self.page.locator("text=No members found").first.is_visible()

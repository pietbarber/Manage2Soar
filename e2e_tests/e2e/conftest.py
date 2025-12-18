"""
Pytest fixtures for end-to-end browser testing with Playwright and Django.

This module provides fixtures that integrate Playwright with Django's
StaticLiveServerTestCase, enabling browser-based testing of JavaScript
functionality.

Issue #389: Playwright-pytest integration for automated browser tests.
"""

import os

import pytest
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright

from members.models import Member
from siteconfig.models import MembershipStatus

# Test password used across all E2E tests
TEST_PASSWORD = "testpass123"


class DjangoPlaywrightTestCase(StaticLiveServerTestCase):
    """
    Base test case that combines Django's live server with Playwright.

    This allows testing JavaScript and browser-based interactions
    against a running Django server with static files served correctly.

    IMPORTANT: Sets DJANGO_ALLOW_ASYNC_UNSAFE in setUpClass to allow Django ORM
    operations in Playwright's async context. While cleaned up in tearDownClass,
    this affects the entire Python process during test execution. E2E tests using
    this base class MUST NOT be run in parallel to avoid race conditions and
    unintended side effects.

    When running E2E tests, use: pytest e2e_tests/ -n 0 (or omit -n flag)
    """

    @classmethod
    def setUpClass(cls):
        # CRITICAL: Allow Django ORM operations in Playwright's async context
        # This affects the entire Python process, not just this test class.
        # WARNING: Do NOT run E2E tests in parallel - use pytest without -n flag
        # or explicitly set -n 0 to prevent race conditions.
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

        super().setUpClass()
        # Start Playwright once for the test class
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

        # Clean up the environment variable
        os.environ.pop("DJANGO_ALLOW_ASYNC_UNSAFE", None)

        super().tearDownClass()

    def setUp(self):
        super().setUp()
        # Create a new browser context for each test (isolated cookies, etc.)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def tearDown(self):
        self.page.close()
        self.context.close()
        super().tearDown()

    def create_test_member(self, username="testuser", is_superuser=False, **kwargs):
        """Create a test member for authentication."""
        # Ensure we have a membership status
        status, _ = MembershipStatus.objects.get_or_create(
            name="Full Member",
            defaults={
                "is_active": True,
                "sort_order": 1,
            },
        )

        defaults = {
            "first_name": "Test",
            "last_name": "User",
            "email": f"{username}@example.com",
            "membership_status": status.name,
            "is_superuser": is_superuser,
            "is_staff": is_superuser,
        }
        defaults.update(kwargs)

        member = Member.objects.create_user(
            username=username,
            password=TEST_PASSWORD,
            **defaults,
        )
        return member

    def login(self, username="testuser", password=TEST_PASSWORD):
        """Log in the user via the browser.

        Raises:
            AssertionError: If login fails or redirect doesn't occur.
        """
        self.page.goto(f"{self.live_server_url}/login/")
        self.page.fill('input[name="username"]', username)
        self.page.fill('input[name="password"]', password)
        self.page.click('button[type="submit"]')
        # Wait for redirect after login
        self.page.wait_for_url(f"{self.live_server_url}/**")

        # Verify login was successful - check we're not still on login page
        current_url = self.page.url
        assert (
            "/login/" not in current_url
        ), f"Login failed - still on login page: {current_url}"


# Pytest fixtures for standalone Playwright tests (without Django test case)


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Configure Playwright browser launch arguments."""
    return {"headless": True}


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure Playwright browser context arguments.

    Note: ignore_https_errors is set to True because Django's StaticLiveServerTestCase
    runs a local development server without SSL certificates. This is safe for E2E tests
    as they run against localhost only, not production environments.
    """
    return {
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,  # Safe for local test server without SSL
    }


@pytest.fixture
def authenticated_page(page, live_server, django_user_model):
    """
    Provide a Playwright page with an authenticated user session.

    Creates a test user and logs in before returning the page.
    Uses get_or_create to avoid IntegrityError in parallel test execution.
    """
    from siteconfig.models import MembershipStatus

    # Ensure we have a membership status
    status, _ = MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "sort_order": 1,
        },
    )

    # Create or get test user - use get_or_create to avoid IntegrityError
    user, created = django_user_model.objects.get_or_create(
        username="e2e_testuser",
        defaults={
            "password": TEST_PASSWORD,
            "email": "e2e_test@example.com",
            "first_name": "E2E",
            "last_name": "Tester",
            "membership_status": status.name,
        },
    )
    if created:
        user.set_password(TEST_PASSWORD)
        user.save()

    # Login via browser
    page.goto(f"{live_server.url}/login/")
    page.fill('input[name="username"]', "e2e_testuser")
    page.fill('input[name="password"]', TEST_PASSWORD)
    page.click('button[type="submit"]')

    # Wait for login to complete
    page.wait_for_url(f"{live_server.url}/**")

    return page


@pytest.fixture
def admin_page(page, live_server, django_user_model):
    """
    Provide a Playwright page with an admin user session.

    Creates a superuser and logs in before returning the page.
    Uses get_or_create to avoid IntegrityError in parallel test execution.
    """
    from siteconfig.models import MembershipStatus

    # Ensure we have a membership status
    status, _ = MembershipStatus.objects.get_or_create(
        name="Full Member",
        defaults={
            "is_active": True,
            "sort_order": 1,
        },
    )

    # Create or get admin user - use get_or_create to avoid IntegrityError
    admin, created = django_user_model.objects.get_or_create(
        username="e2e_admin",
        defaults={
            "password": TEST_PASSWORD,
            "email": "e2e_admin@example.com",
            "first_name": "Admin",
            "last_name": "User",
            "membership_status": status.name,
            "is_superuser": True,
            "is_staff": True,
        },
    )
    if created:
        admin.set_password(TEST_PASSWORD)
        admin.save()

    # Login via browser
    page.goto(f"{live_server.url}/login/")
    page.fill('input[name="username"]', "e2e_admin")
    page.fill('input[name="password"]', TEST_PASSWORD)
    page.click('button[type="submit"]')

    # Wait for login to complete
    page.wait_for_url(f"{live_server.url}/**")

    return page

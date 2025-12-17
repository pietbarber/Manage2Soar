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

# Allow Django ORM operations in Playwright's async context
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


class DjangoPlaywrightTestCase(StaticLiveServerTestCase):
    """
    Base test case that combines Django's live server with Playwright.

    This allows testing JavaScript and browser-based interactions
    against a running Django server with static files served correctly.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Start Playwright once for the test class
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
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
            password="testpass123",
            **defaults,
        )
        return member

    def login(self, username="testuser", password="testpass123"):
        """Log in the user via the browser."""
        self.page.goto(f"{self.live_server_url}/login/")
        self.page.fill('input[name="username"]', username)
        self.page.fill('input[name="password"]', password)
        self.page.click('button[type="submit"]')
        # Wait for redirect after login
        self.page.wait_for_url(f"{self.live_server_url}/**")


# Pytest fixtures for standalone Playwright tests (without Django test case)


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Configure Playwright browser launch arguments."""
    return {"headless": True}


@pytest.fixture(scope="session")
def browser_context_args():
    """Configure Playwright browser context arguments."""
    return {
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
    }


@pytest.fixture
def live_server(live_server):
    """
    Provide the Django live server URL to Playwright tests.

    This uses pytest-django's live_server fixture.
    """
    return live_server


@pytest.fixture
def authenticated_page(page, live_server, django_user_model):
    """
    Provide a Playwright page with an authenticated user session.

    Creates a test user and logs in before returning the page.
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

    # Create test user
    user = django_user_model.objects.create_user(
        username="e2e_testuser",
        password="testpass123",
        email="e2e_test@example.com",
        first_name="E2E",
        last_name="Tester",
        membership_status=status.name,
    )

    # Login via browser
    page.goto(f"{live_server.url}/login/")
    page.fill('input[name="username"]', "e2e_testuser")
    page.fill('input[name="password"]', "testpass123")
    page.click('button[type="submit"]')

    # Wait for login to complete
    page.wait_for_url(f"{live_server.url}/**")

    return page


@pytest.fixture
def admin_page(page, live_server, django_user_model):
    """
    Provide a Playwright page with an admin user session.

    Creates a superuser and logs in before returning the page.
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

    # Create admin user
    user = django_user_model.objects.create_superuser(
        username="e2e_admin",
        password="adminpass123",
        email="e2e_admin@example.com",
        first_name="Admin",
        last_name="User",
        membership_status=status.name,
    )

    # Login via browser
    page.goto(f"{live_server.url}/login/")
    page.fill('input[name="username"]', "e2e_admin")
    page.fill('input[name="password"]', "adminpass123")
    page.click('button[type="submit"]')

    # Wait for login to complete
    page.wait_for_url(f"{live_server.url}/**")

    return page

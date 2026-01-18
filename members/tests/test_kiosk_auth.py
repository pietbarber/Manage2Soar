"""
Tests for Kiosk Token Authentication (Issue #364).

Tests cover:
- KioskToken model functionality
- Device binding and fingerprint validation
- Magic URL authentication flow
- Auto-reauth middleware
- Admin interface
- Security scenarios (stolen tokens, fingerprint mismatches)
"""

import json

from django.contrib.auth import get_user
from django.test import Client, TestCase
from django.urls import reverse

from members.models import KioskAccessLog, KioskToken, Member
from siteconfig.models import MembershipStatus


class KioskTokenModelTests(TestCase):
    """Tests for the KioskToken model."""

    @classmethod
    def setUpTestData(cls):
        """Create a role account for testing."""
        cls.role_user = Member.objects.create_user(
            username="kiosk-laptop",
            email="kiosk@example.com",
            password=None,  # No password for role account
            first_name="Club",
            last_name="Laptop",
            membership_status="Role Account",
        )

    def test_token_generated_on_create(self):
        """Token should be auto-generated when creating a KioskToken."""
        token = KioskToken.objects.create(
            user=self.role_user,
            name="Test Kiosk",
        )
        self.assertIsNotNone(token.token)
        self.assertGreater(len(token.token), 32)  # Should be a long secure token

    def test_token_uniqueness(self):
        """Each token should be unique."""
        token1 = KioskToken.objects.create(user=self.role_user, name="Kiosk 1")
        token2 = KioskToken.objects.create(user=self.role_user, name="Kiosk 2")
        self.assertNotEqual(token1.token, token2.token)

    def test_regenerate_token(self):
        """Regenerating should create a new token and clear fingerprint."""
        token = KioskToken.objects.create(
            user=self.role_user,
            name="Test Kiosk",
            device_fingerprint="abc123",
        )
        old_token = token.token

        new_token = token.regenerate_token()

        self.assertNotEqual(old_token, new_token)
        self.assertEqual(token.token, new_token)
        self.assertIsNone(token.device_fingerprint)  # Should be cleared

    def test_device_binding(self):
        """Device binding should store the fingerprint."""
        token = KioskToken.objects.create(user=self.role_user, name="Test Kiosk")
        self.assertFalse(token.is_device_bound())

        token.bind_device("fingerprint_hash_123")

        self.assertTrue(token.is_device_bound())
        self.assertEqual(token.device_fingerprint, "fingerprint_hash_123")

    def test_fingerprint_validation_unbound(self):
        """Unbound token should accept any fingerprint."""
        token = KioskToken.objects.create(user=self.role_user, name="Test Kiosk")
        self.assertTrue(token.validate_fingerprint("any_fingerprint"))

    def test_fingerprint_validation_bound_matching(self):
        """Bound token should accept matching fingerprint."""
        token = KioskToken.objects.create(
            user=self.role_user,
            name="Test Kiosk",
            device_fingerprint="correct_fingerprint",
        )
        self.assertTrue(token.validate_fingerprint("correct_fingerprint"))

    def test_fingerprint_validation_bound_mismatch(self):
        """Bound token should reject non-matching fingerprint."""
        token = KioskToken.objects.create(
            user=self.role_user,
            name="Test Kiosk",
            device_fingerprint="correct_fingerprint",
        )
        self.assertFalse(token.validate_fingerprint("wrong_fingerprint"))

    def test_get_magic_url(self):
        """Magic URL should be generated correctly."""
        token = KioskToken.objects.create(user=self.role_user, name="Test Kiosk")
        url = token.get_magic_url()
        self.assertIn("/members/kiosk/", url)
        self.assertIn(token.token, url)

    def test_record_usage(self):
        """Record usage should update last_used_at and IP."""
        token = KioskToken.objects.create(user=self.role_user, name="Test Kiosk")
        self.assertIsNone(token.last_used_at)
        self.assertIsNone(token.last_used_ip)

        token.record_usage("192.168.1.1")
        token.refresh_from_db()

        self.assertIsNotNone(token.last_used_at)
        self.assertEqual(token.last_used_ip, "192.168.1.1")


class KioskLoginViewTests(TestCase):
    """Tests for the kiosk login views."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.role_user = Member.objects.create_user(
            username="kiosk-laptop",
            email="kiosk@example.com",
            password=None,
            first_name="Club",
            last_name="Laptop",
            membership_status="Role Account",
        )
        cls.active_token = KioskToken.objects.create(
            user=cls.role_user,
            name="Active Kiosk",
            is_active=True,
        )
        cls.inactive_token = KioskToken.objects.create(
            user=cls.role_user,
            name="Inactive Kiosk",
            is_active=False,
        )
        cls.bound_token = KioskToken.objects.create(
            user=cls.role_user,
            name="Bound Kiosk",
            is_active=True,
            device_fingerprint="bound_device_fingerprint",
        )

    def test_invalid_token_returns_403(self):
        """Invalid token should return 403 error page."""
        response = self.client.get("/members/kiosk/invalid_token_123/")
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Access Denied", status_code=403)

    def test_inactive_token_returns_403(self):
        """Inactive/revoked token should return 403."""
        url = self.inactive_token.get_magic_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response, "This kiosk access link has been disabled", status_code=403
        )

    def test_unbound_token_shows_binding_page(self):
        """Unbound token should show the device binding page."""
        url = self.active_token.get_magic_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Device Registration")
        self.assertContains(response, "Registering this device")

    def test_bound_token_shows_verify_page(self):
        """Bound token should show the device verification page."""
        url = self.bound_token.get_magic_url()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Device Verification")


class KioskBindDeviceTests(TestCase):
    """Tests for the device binding endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.role_user = Member.objects.create_user(
            username="kiosk-laptop",
            email="kiosk@example.com",
            password=None,
            first_name="Club",
            last_name="Laptop",
            membership_status="Role Account",
        )
        cls.token = KioskToken.objects.create(
            user=cls.role_user,
            name="Test Kiosk",
            is_active=True,
            landing_page="logsheet:index",
        )

    def test_bind_device_success(self):
        """Successful device binding should log in user and set cookies."""
        url = reverse("members:kiosk_bind_device", kwargs={"token": self.token.token})
        response = self.client.post(
            url,
            data=json.dumps({"fingerprint": "test_fingerprint_data"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("redirect", data)

        # Check cookies were set
        self.assertIn("kiosk_token", response.cookies)
        self.assertIn("kiosk_fingerprint", response.cookies)

        # Check device was bound
        self.token.refresh_from_db()
        self.assertTrue(self.token.is_device_bound())

        # Check access log was created
        log = KioskAccessLog.objects.filter(kiosk_token=self.token).last()
        self.assertIsNotNone(log)
        assert log is not None  # Type narrowing for Pylance
        self.assertEqual(log.status, "bound")

    def test_bind_device_missing_fingerprint(self):
        """Missing fingerprint should return 400."""
        url = reverse("members:kiosk_bind_device", kwargs={"token": self.token.token})
        response = self.client.post(
            url,
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_bind_device_invalid_token(self):
        """Invalid token should return 403."""
        url = reverse("members:kiosk_bind_device", kwargs={"token": "invalid"})
        response = self.client.post(
            url,
            data=json.dumps({"fingerprint": "test"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)


class KioskVerifyDeviceTests(TestCase):
    """Tests for the device verification endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.role_user = Member.objects.create_user(
            username="kiosk-laptop",
            email="kiosk@example.com",
            password=None,
            first_name="Club",
            last_name="Laptop",
            membership_status="Role Account",
        )
        # Pre-bind with a known fingerprint hash
        import hashlib

        cls.fingerprint_raw = "device_fingerprint_data"
        cls.fingerprint_hash = hashlib.sha256(cls.fingerprint_raw.encode()).hexdigest()

        cls.token = KioskToken.objects.create(
            user=cls.role_user,
            name="Bound Kiosk",
            is_active=True,
            device_fingerprint=cls.fingerprint_hash,
            landing_page="logsheet:index",
        )

    def test_verify_matching_fingerprint(self):
        """Matching fingerprint should succeed."""
        url = reverse("members:kiosk_verify_device", kwargs={"token": self.token.token})
        response = self.client.post(
            url,
            data=json.dumps({"fingerprint": self.fingerprint_raw}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

    def test_verify_mismatched_fingerprint(self):
        """Non-matching fingerprint should return 403."""
        url = reverse("members:kiosk_verify_device", kwargs={"token": self.token.token})
        response = self.client.post(
            url,
            data=json.dumps({"fingerprint": "wrong_fingerprint"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("error", data)

        # Check security event was logged
        log = KioskAccessLog.objects.filter(
            kiosk_token=self.token, status="fingerprint_mismatch"
        ).last()
        self.assertIsNotNone(log)


class KioskAutoLoginMiddlewareTests(TestCase):
    """Tests for the auto-login middleware."""

    @classmethod
    def setUpTestData(cls):
        # Ensure Role Account membership status exists and is active
        status, created = MembershipStatus.objects.get_or_create(
            name="Role Account", defaults={"is_active": True}
        )
        if not status.is_active:
            status.is_active = True
            status.save()

        cls.role_user = Member.objects.create_user(
            username="kiosk-laptop",
            email="kiosk@example.com",
            password=None,
            first_name="Club",
            last_name="Laptop",
            membership_status="Role Account",
        )
        import hashlib

        cls.fingerprint_hash = hashlib.sha256(b"device_fp").hexdigest()
        cls.token = KioskToken.objects.create(
            user=cls.role_user,
            name="Bound Kiosk",
            is_active=True,
            device_fingerprint=cls.fingerprint_hash,
            landing_page="logsheet:index",
        )

    def test_auto_login_with_valid_cookies(self):
        """Middleware should auto-login with valid kiosk cookies."""
        client = Client()

        # Set cookies manually
        client.cookies["kiosk_token"] = self.token.token
        client.cookies["kiosk_fingerprint"] = self.fingerprint_hash

        # Access a protected page (member list requires authentication)
        client.get("/members/", follow=True)

        # Should be authenticated now
        user = get_user(client)
        self.assertTrue(user.is_authenticated)
        self.assertEqual(user.username, "kiosk-laptop")

        # Verify successful auto-reauth created access log for audit trail
        logs = KioskAccessLog.objects.filter(kiosk_token=self.token, status="success")
        self.assertGreater(logs.count(), 0)

    def test_no_auto_login_with_invalid_token(self):
        """Middleware should not auto-login with invalid token."""
        client = Client()

        client.cookies["kiosk_token"] = "invalid_token"
        client.cookies["kiosk_fingerprint"] = self.fingerprint_hash

        # Access a page
        response = client.get("/members/", follow=True)

        # Should redirect to login (not authenticated)
        self.assertIn("/login/", response.request["PATH_INFO"])

    def test_no_auto_login_with_wrong_fingerprint(self):
        """Middleware should not auto-login with wrong fingerprint."""
        client = Client()

        client.cookies["kiosk_token"] = self.token.token
        client.cookies["kiosk_fingerprint"] = "wrong_fingerprint"

        # Access a page
        response = client.get("/members/", follow=True)

        # Should redirect to login
        self.assertIn("/login/", response.request["PATH_INFO"])

        # Verify fingerprint_mismatch access log was created for security audit
        logs = KioskAccessLog.objects.filter(
            kiosk_token=self.token, status="fingerprint_mismatch"
        )
        self.assertGreater(logs.count(), 0)


class KioskAccessLogTests(TestCase):
    """Tests for the access log model."""

    @classmethod
    def setUpTestData(cls):
        cls.role_user = Member.objects.create_user(
            username="kiosk-laptop",
            email="kiosk@example.com",
            password=None,
            membership_status="Role Account",
        )
        cls.token = KioskToken.objects.create(
            user=cls.role_user,
            name="Test Kiosk",
            is_active=True,
            landing_page="logsheet:index",
        )

    def test_access_log_created_on_success(self):
        """Successful login should create access log."""
        url = reverse("members:kiosk_bind_device", kwargs={"token": self.token.token})
        self.client.post(
            url,
            data=json.dumps({"fingerprint": "test_fp"}),
            content_type="application/json",
        )

        logs = KioskAccessLog.objects.filter(kiosk_token=self.token)
        self.assertGreater(logs.count(), 0)

    def test_access_log_created_on_failure(self):
        """Failed login attempt should create access log."""
        self.client.get("/members/kiosk/nonexistent_token/")

        logs = KioskAccessLog.objects.filter(status="invalid_token")
        self.assertGreater(logs.count(), 0)


class KioskSecurityTests(TestCase):
    """Security-focused tests for kiosk authentication."""

    @classmethod
    def setUpTestData(cls):
        cls.role_user = Member.objects.create_user(
            username="kiosk-laptop",
            email="kiosk@example.com",
            password=None,
            membership_status="Role Account",
        )

    def test_stolen_url_different_device(self):
        """Stolen URL should not work on a different device."""
        import hashlib

        # Original device binds
        token = KioskToken.objects.create(
            user=self.role_user,
            name="Original Device",
            is_active=True,
        )

        # Simulate original device binding
        original_fp = "original_device_fingerprint"
        original_fp_hash = hashlib.sha256(original_fp.encode()).hexdigest()
        token.bind_device(original_fp_hash)

        # Attacker tries with stolen URL but different device
        url = reverse("members:kiosk_verify_device", kwargs={"token": token.token})
        response = self.client.post(
            url,
            data=json.dumps({"fingerprint": "attacker_device_fingerprint"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Device verification failed", response.json()["error"])

    def test_revoked_token_cannot_authenticate(self):
        """Revoked token should not allow authentication."""
        token = KioskToken.objects.create(
            user=self.role_user,
            name="Revoked Token",
            is_active=False,
        )

        url = token.get_magic_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "This kiosk access link has been disabled. Please contact an administrator.",
            status_code=403,
        )

    def test_token_regeneration_invalidates_old_url(self):
        """After regeneration, old URL should not work."""
        token = KioskToken.objects.create(
            user=self.role_user,
            name="Regenerated Token",
            is_active=True,
        )

        old_url = token.get_magic_url()

        # Regenerate
        token.regenerate_token()

        # Old URL should fail
        response = self.client.get(old_url)
        self.assertEqual(response.status_code, 403)

        # New URL should work
        new_url = token.get_magic_url()
        response = self.client.get(new_url)
        self.assertEqual(response.status_code, 200)


class KioskActiveMemberDecoratorTests(TestCase):
    """
    Tests for @active_member_required decorator interaction with kiosk sessions (Issue #486).

    These tests verify that kiosk-authenticated users bypass membership_status checks
    while non-kiosk users still require valid membership_status.
    """

    @classmethod
    def setUpTestData(cls):
        """Create test users and membership statuses."""
        # Create active membership status
        MembershipStatus.objects.create(
            name="Full Member", is_active=True, display_order=1
        )
        # Create inactive membership status
        MembershipStatus.objects.create(
            name="Inactive", is_active=False, display_order=99
        )
        # Create role account status
        MembershipStatus.objects.create(
            name="Role Account", is_active=False, display_order=100
        )

    def setUp(self):
        """Create test data for each test."""
        # Create role account for kiosk (no valid membership_status)
        self.kiosk_user = Member.objects.create_user(
            username="club-laptop",
            email="invalid@invalid",
            password=None,
            first_name="Club",
            last_name="Laptop",
            membership_status="Role Account",
        )

        # Create kiosk token for the role account
        self.kiosk_token = KioskToken.objects.create(
            user=self.kiosk_user, name="Test Kiosk", is_active=True
        )

        # Bind device with fingerprint
        fingerprint_hash = "test_fingerprint_hash_" + "a" * 40
        self.kiosk_token.bind_device(fingerprint_hash)

        # Create normal user with inactive membership_status
        self.inactive_user = Member.objects.create_user(
            username="inactive",
            email="inactive@example.com",
            password="testpass123",
            first_name="Inactive",
            last_name="User",
            membership_status="Inactive",
        )

        # Create normal user with active membership_status
        self.active_user = Member.objects.create_user(
            username="active",
            email="active@example.com",
            password="testpass123",
            first_name="Active",
            last_name="User",
            membership_status="Full Member",
        )

    def test_kiosk_session_bypasses_membership_check(self):
        """Kiosk-authenticated users should access @active_member_required views."""
        # Bind device and log in via kiosk
        bind_url = reverse(
            "members:kiosk_bind_device", kwargs={"token": self.kiosk_token.token}
        )
        response = self.client.post(
            bind_url,
            data=json.dumps({"fingerprint": "test_fingerprint_" + "a" * 40}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Verify session flag is set
        session = self.client.session
        self.assertTrue(session.get("is_kiosk_authenticated"))

        # Access a view with @active_member_required (member_list)
        # Role account has inactive membership_status but should be allowed
        member_list_url = reverse("members:member_list")
        response = self.client.get(member_list_url)
        self.assertEqual(
            response.status_code,
            200,
            "Kiosk session should bypass membership_status check",
        )

    def test_non_kiosk_inactive_member_denied(self):
        """Non-kiosk users with inactive membership_status should be denied."""
        # Log in as inactive user via normal Django authentication
        self.client.login(username="inactive", password="testpass123")

        # Verify NO kiosk session flag
        session = self.client.session
        self.assertFalse(session.get("is_kiosk_authenticated", False))

        # Access a view with @active_member_required
        member_list_url = reverse("members:member_list")
        response = self.client.get(member_list_url)
        self.assertEqual(
            response.status_code, 403, "Inactive user should be denied access"
        )

    def test_non_kiosk_active_member_allowed(self):
        """Non-kiosk users with active membership_status should be allowed."""
        # Log in as active user via normal Django authentication
        self.client.login(username="active", password="testpass123")

        # Verify NO kiosk session flag
        session = self.client.session
        self.assertFalse(session.get("is_kiosk_authenticated", False))

        # Access a view with @active_member_required
        member_list_url = reverse("members:member_list")
        response = self.client.get(member_list_url)
        self.assertEqual(
            response.status_code, 200, "Active member should be allowed access"
        )

    def test_stale_kiosk_cookies_with_oauth_login_denied(self):
        """
        Security test: Users with stale kiosk cookies but non-kiosk authentication
        should NOT bypass membership_status checks (Issue #486).

        Scenario:
        1. User authenticates via kiosk, gets cookies
        2. Kiosk token is revoked
        3. User logs out, logs in via OAuth2 with inactive membership_status
        4. Old kiosk cookies still present in browser
        5. Should be DENIED because session flag not set (middleware didn't auth via kiosk)
        """
        # Set stale kiosk cookies manually (simulating leftover from previous session)
        self.client.cookies["kiosk_token"] = self.kiosk_token.token
        # Assert fingerprint is set (device was bound in setUp)
        self.assertIsNotNone(self.kiosk_token.device_fingerprint)
        fingerprint = self.kiosk_token.device_fingerprint
        assert fingerprint is not None  # Type narrowing for Pylance
        self.client.cookies["kiosk_fingerprint"] = fingerprint

        # Log in as inactive user via Django authentication (simulating OAuth2)
        self.client.login(username="inactive", password="testpass123")

        # Verify session has NO kiosk flag (middleware didn't authenticate via kiosk)
        session = self.client.session
        self.assertFalse(
            session.get("is_kiosk_authenticated", False),
            "Session should not have kiosk flag for non-kiosk authentication",
        )

        # Access a view with @active_member_required
        member_list_url = reverse("members:member_list")
        response = self.client.get(member_list_url)
        self.assertEqual(
            response.status_code,
            403,
            "Stale kiosk cookies should NOT bypass membership check",
        )

    def test_kiosk_middleware_sets_session_flag(self):
        """Middleware should set is_kiosk_authenticated session flag on auto-reauth."""
        # First, bind device and log in to set cookies
        bind_url = reverse(
            "members:kiosk_bind_device", kwargs={"token": self.kiosk_token.token}
        )
        response = self.client.post(
            bind_url,
            data=json.dumps({"fingerprint": "test_fingerprint_" + "a" * 40}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Extract cookies from response
        kiosk_token_cookie = response.cookies.get("kiosk_token")
        kiosk_fingerprint_cookie = response.cookies.get("kiosk_fingerprint")
        self.assertIsNotNone(kiosk_token_cookie)
        self.assertIsNotNone(kiosk_fingerprint_cookie)

        # Log out (clears session but cookies remain)
        self.client.logout()

        # Verify user is not authenticated
        user = get_user(self.client)
        self.assertFalse(user.is_authenticated)

        # Access any page - middleware should auto-reauth via cookies
        member_list_url = reverse("members:member_list")
        response = self.client.get(member_list_url)

        # Verify user is now authenticated
        user = get_user(self.client)
        self.assertTrue(user.is_authenticated)

        # Verify session flag is set by middleware
        session = self.client.session
        self.assertTrue(
            session.get("is_kiosk_authenticated"),
            "Middleware should set is_kiosk_authenticated flag on auto-reauth",
        )

        # Verify access is granted
        self.assertEqual(
            response.status_code,
            200,
            "Auto-reauthed kiosk session should have access",
        )

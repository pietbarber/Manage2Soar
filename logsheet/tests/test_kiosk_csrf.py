"""
Regression tests for Issue #709: Kiosk CSRF 403 on logsheet POST actions.

Root cause: KioskAutoLoginMiddleware called login() → rotate_token(), which replaced
request.META["CSRF_COOKIE"] with a new secret AFTER CsrfViewMiddleware.process_request
had already stored the correct secret there.  CsrfViewMiddleware.process_view then
compared the POST token against the rotated (wrong) secret → 403.

Fix: Move KioskAutoLoginMiddleware before CsrfViewMiddleware in MIDDLEWARE so that
CsrfViewMiddleware.process_request runs after the rotation and overwrites the rotated
secret with the stable cookie value.
"""

import json
import re
from datetime import date, time

from django.conf import settings
from django.test import Client, TestCase
from django.urls import reverse

from logsheet.models import Airfield, Flight, Glider, Logsheet
from members.models import KioskToken, Member


class KioskMiddlewareOrderTest(TestCase):
    """Verify the MIDDLEWARE list is ordered correctly for kiosk CSRF safety."""

    def test_kiosk_middleware_before_csrf_middleware(self):
        """
        KioskAutoLoginMiddleware MUST appear before CsrfViewMiddleware.

        If this ordering is wrong, login() → rotate_token() will corrupt
        request.META["CSRF_COOKIE"] before CSRF validation, causing every
        kiosk POST to return 403 (Issue #709).
        """
        middleware = settings.MIDDLEWARE
        kiosk_idx = next(
            (i for i, m in enumerate(middleware) if "KioskAutoLoginMiddleware" in m),
            None,
        )
        csrf_idx = next(
            (i for i, m in enumerate(middleware) if "CsrfViewMiddleware" in m),
            None,
        )
        self.assertIsNotNone(
            kiosk_idx, "KioskAutoLoginMiddleware not found in MIDDLEWARE"
        )
        self.assertIsNotNone(csrf_idx, "CsrfViewMiddleware not found in MIDDLEWARE")
        self.assertLess(
            kiosk_idx,
            csrf_idx,
            f"KioskAutoLoginMiddleware (idx {kiosk_idx}) must be before "
            f"CsrfViewMiddleware (idx {csrf_idx}) — see Issue #709.",
        )

    def test_auth_middleware_before_kiosk_middleware(self):
        """
        AuthenticationMiddleware must appear before KioskAutoLoginMiddleware so that
        request.user is available for the is_authenticated check.
        """
        middleware = settings.MIDDLEWARE
        auth_idx = next(
            (
                i
                for i, m in enumerate(middleware)
                if m == "django.contrib.auth.middleware.AuthenticationMiddleware"
            ),
            None,
        )
        kiosk_idx = next(
            (i for i, m in enumerate(middleware) if "KioskAutoLoginMiddleware" in m),
            None,
        )
        self.assertIsNotNone(
            auth_idx, "AuthenticationMiddleware not found in MIDDLEWARE"
        )
        self.assertIsNotNone(
            kiosk_idx, "KioskAutoLoginMiddleware not found in MIDDLEWARE"
        )
        self.assertLess(
            auth_idx,
            kiosk_idx,
            f"AuthenticationMiddleware (idx {auth_idx}) must be before "
            f"KioskAutoLoginMiddleware (idx {kiosk_idx}).",
        )


class KioskCsrfRegressionTest(TestCase):
    """
    End-to-end regression tests for Issue #709.

    Uses Client(enforce_csrf_checks=True) so that CSRF validation is fully active,
    matching real production behaviour.
    """

    @classmethod
    def setUpTestData(cls):
        # Kiosk role account — membership_status is irrelevant because
        # active_member_required bypasses the status check for kiosk sessions.
        cls.kiosk_user = Member.objects.create_user(
            username="kiosk-test-laptop",
            email="kiosktest@example.com",
            password=None,
            first_name="Kiosk",
            last_name="Laptop",
            membership_status="Role Account",
        )
        # Fingerprint stored directly (compare_fingerprint does exact string match)
        cls.fingerprint = "test_device_fingerprint_hash_abc123"
        cls.kiosk_token = KioskToken.objects.create(
            user=cls.kiosk_user,
            name="Test Kiosk",
            is_active=True,
            device_fingerprint=cls.fingerprint,
        )

        # Logsheet + flight needed for land/launch endpoints
        cls.airfield = Airfield.objects.create(
            identifier="KFRR", name="Front Royal Airport", is_active=True
        )
        cls.glider = Glider.objects.create(
            n_number="N709TK", club_owned=True, is_active=True
        )
        cls.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=cls.airfield,
            created_by=cls.kiosk_user,
        )
        # Flight without a launch time — ready for launch_flight_now
        cls.flight = Flight.objects.create(
            logsheet=cls.logsheet,
            glider=cls.glider,
        )

    def _csrf_client(self):
        """Return a Client with CSRF enforcement and kiosk cookies pre-set."""
        client = Client(enforce_csrf_checks=True)
        client.cookies["kiosk_token"] = self.kiosk_token.token
        client.cookies["kiosk_fingerprint"] = self.fingerprint
        return client

    @staticmethod
    def _extract_csrf_token(html):
        """Parse the masked CSRF token rendered by {% csrf_token %} in the page."""
        # Try both attribute orderings Django may render
        for pattern in (
            r'name="csrfmiddlewaretoken"\s+value="([^"]+)"',
            r'value="([^"]+)"\s+name="csrfmiddlewaretoken"',
        ):
            m = re.search(pattern, html)
            if m:
                return m.group(1)
        return None

    def test_kiosk_launch_post_csrf_active_session(self):
        """
        Happy path: kiosk session is active (no expiry), POST with valid CSRF token
        must not return 403.
        """
        client = self._csrf_client()
        manage_url = reverse("logsheet:manage", kwargs={"pk": self.logsheet.pk})

        response = client.get(manage_url)
        self.assertEqual(response.status_code, 200)

        csrf_token = self._extract_csrf_token(response.content.decode())
        self.assertIsNotNone(csrf_token, "CSRF token not found in manage page HTML")

        launch_url = reverse(
            "logsheet:launch_flight_now", kwargs={"flight_id": self.flight.pk}
        )
        response = client.post(
            launch_url,
            data=json.dumps({"launch_time": "10:00"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertNotEqual(
            response.status_code,
            403,
            "CSRF 403 on kiosk POST with active session — unexpected regression.",
        )

    def test_kiosk_launch_post_csrf_after_session_expiry(self):
        """
        Regression case for Issue #709.

        Sequence:
          1. GET manage page   → kiosk middleware authenticates, CSRF cookie set.
          2. Session is flushed (server-side expiry simulated).
          3. POST launch_now   → kiosk middleware re-auths via cookies (login() →
             rotate_token()). With the correct middleware ordering, CsrfViewMiddleware
             overwrites the rotated META["CSRF_COOKIE"] with the stable cookie secret,
             so the token from step 1 still validates.

        Before the fix this step 3 always returned 403.
        """
        client = self._csrf_client()
        manage_url = reverse("logsheet:manage", kwargs={"pk": self.logsheet.pk})

        # Step 1: GET to establish CSRF cookie and session
        response = client.get(manage_url)
        self.assertEqual(response.status_code, 200)
        csrf_token = self._extract_csrf_token(response.content.decode())
        self.assertIsNotNone(csrf_token, "CSRF token not found in manage page HTML")

        # Step 2: Simulate session expiry by deleting the server-side session.
        # The client still has the (now-invalid) session cookie, so the next
        # request will see an anonymous user → kiosk middleware re-auths.
        client.session.flush()

        # Step 3: POST with the CSRF token from step 1.
        # The kiosk middleware will re-authenticate (rotate_token is called).
        # With the middleware ordering fix, this must NOT return 403.
        launch_url = reverse(
            "logsheet:launch_flight_now", kwargs={"flight_id": self.flight.pk}
        )
        response = client.post(
            launch_url,
            data=json.dumps({"launch_time": "10:00"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertNotEqual(
            response.status_code,
            403,
            "CSRF 403 after kiosk session expiry — Issue #709 middleware "
            "ordering regression detected!",
        )

    def test_kiosk_land_post_csrf_after_session_expiry(self):
        """Same regression test for land_flight_now (Issue #709)."""
        # Create a fresh flight with a launch_time so landing is valid.
        # Using a local object avoids mutating the shared setUpTestData flight.
        landing_flight = Flight.objects.create(
            logsheet=self.logsheet,
            glider=self.glider,
            launch_time=time(10, 0),
        )

        client = self._csrf_client()
        manage_url = reverse("logsheet:manage", kwargs={"pk": self.logsheet.pk})

        response = client.get(manage_url)
        self.assertEqual(response.status_code, 200)
        csrf_token = self._extract_csrf_token(response.content.decode())
        self.assertIsNotNone(csrf_token)

        client.session.flush()

        land_url = reverse(
            "logsheet:land_flight_now", kwargs={"flight_id": landing_flight.pk}
        )
        response = client.post(
            land_url,
            data=json.dumps({"landing_time": "11:00"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertNotEqual(
            response.status_code,
            403,
            "CSRF 403 after kiosk session expiry on land endpoint — Issue #709 regression!",
        )

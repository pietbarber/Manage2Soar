"""
E2E tests for logsheet Launch Now / Land Now button error handling (Issue #707).

Verifies:
1. Online happy path: clicking Launch/Land Now calls the server, page reloads,
   flight status updates — no spurious offline-pending state.
2. Server error path: when the server returns a non-JSON error (500), the
   handler shows an alert dialog instead of silently queuing the operation to
   IndexedDB as "offline pending".

These tests guard against the root-cause regression described in #707 where
`.catch()` was too broad and fired on JSON parse errors from HTML error pages,
causing online flights to enter pending-sync mode.
"""

from datetime import date

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Flight, Glider, Logsheet
from siteconfig.models import SiteConfiguration


class TestLogsheetLaunchLandHandlers(DjangoPlaywrightTestCase):
    """E2E tests for the Launch Now and Land Now button JS handlers."""

    def setUp(self):
        super().setUp()
        self.member = self.create_test_member(username="testpilot", is_superuser=True)
        self.login(username="testpilot")

        self.airfield = Airfield.objects.create(
            identifier="KFRR", name="Front Royal Airport", is_active=True
        )
        self.glider = Glider.objects.create(
            make="Schleicher",
            model="ASK-21",
            n_number="N707AB",
            competition_number="A1",
            seats=2,
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date(2026, 1, 15),
            airfield=self.airfield,
            created_by=self.member,
            duty_officer=self.member,
        )
        # Flight with no launch time (pending)
        self.flight = Flight.objects.create(
            logsheet=self.logsheet,
            pilot=self.member,
            glider=self.glider,
            airfield=self.airfield,
            flight_type="solo",
        )
        # Site config required for manage page to render correctly
        if not SiteConfiguration.objects.first():
            SiteConfiguration.objects.create(
                club_name="Test Club",
                domain_name="test.example.com",
                club_abbreviation="TC",
                quick_altitude_buttons="2000,3000",
            )

    # ------------------------------------------------------------------
    # Happy-path: online launch
    # ------------------------------------------------------------------

    def test_launch_now_online_updates_flight_status(self):
        """
        Clicking 'Launch Now' while connected should POST to the server,
        the page should reload, and the flight badge should change to
        'Flying' — not 'Pending Sync'.
        """
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # The flight should start in Pending status
        pending_badge = self.page.query_selector(".flight-badge-pending")
        assert pending_badge is not None, "Flight should initially be in Pending status"

        # Find the Launch Now button for our flight
        launch_btn = self.page.query_selector(
            f'.launch-now-btn[data-flight-id="{self.flight.pk}"]'
        )
        assert launch_btn is not None, "Launch Now button should be present"

        # Click and wait for the page to reload (JS calls location.reload on success)
        with self.page.expect_navigation():
            launch_btn.click()

        # After reload the flight should show Flying status
        flying_badge = self.page.query_selector(".flight-badge-flying")
        assert (
            flying_badge is not None
        ), "Flight should be in 'Flying' status after a successful launch"

        # Must NOT be stuck in Pending Sync state
        pending_sync_btns = self.page.query_selector_all(
            "button:has-text('Pending Sync')"
        )
        assert (
            len(pending_sync_btns) == 0
        ), "No button should show 'Pending Sync…' after a successful online launch"

    # ------------------------------------------------------------------
    # Server-error path: should alert, NOT queue offline
    # ------------------------------------------------------------------

    def test_launch_now_server_error_shows_alert_not_pending(self):
        """
        When the server returns a 500 HTML response (non-JSON error), the
        handler must show an alert dialog and NOT put the button into
        'Pending Sync…' state.

        This is the regression test for the root cause of Issue #707.
        """
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Intercept the launch_now endpoint and return a 500 HTML page
        self.page.route(
            f"**/logsheet/flight/{self.flight.pk}/launch_now/",
            lambda route: route.fulfill(
                status=500,
                body="<html><body>Internal Server Error</body></html>",
                content_type="text/html",
            ),
        )

        # Capture any alert dialogs
        dialog_messages = []

        def handle_dialog(dialog):
            dialog_messages.append(dialog.message)
            dialog.dismiss()

        self.page.on("dialog", handle_dialog)

        launch_btn = self.page.query_selector(
            f'.launch-now-btn[data-flight-id="{self.flight.pk}"]'
        )
        assert launch_btn is not None

        launch_btn.click()
        # Give JS time to process the response
        self.page.wait_for_timeout(600)

        # An alert should have fired with an error message
        assert (
            len(dialog_messages) > 0
        ), "An alert dialog should appear when the server returns a 500 error"
        msg = dialog_messages[0].lower()
        assert (
            "500" in msg or "could not" in msg or "server error" in msg
        ), f"Alert should describe the server error, got: '{dialog_messages[0]}'"

        # Button must NOT be in the offline-pending state
        btn_class = launch_btn.get_attribute("class") or ""
        assert (
            "btn-warning" not in btn_class
        ), "Launch button should NOT switch to btn-warning (Pending Sync) on a server error"
        btn_text = launch_btn.inner_text()
        assert (
            "Pending Sync" not in btn_text
        ), f"Button text should not say 'Pending Sync', got: '{btn_text}'"

    def test_land_now_server_error_shows_alert_not_pending(self):
        """
        Same regression test as above but for the Land Now button.
        Server 500 should show alert, not queue offline.
        """
        # Give the flight a launch time so the Land Now button appears
        from datetime import time

        self.flight.launch_time = time(10, 0)
        self.flight.save(update_fields=["launch_time"])

        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Intercept the landing_now endpoint with a 500
        self.page.route(
            f"**/logsheet/flight/{self.flight.pk}/landing_now/",
            lambda route: route.fulfill(
                status=500,
                body="<html><body>Internal Server Error</body></html>",
                content_type="text/html",
            ),
        )

        dialog_messages = []

        def handle_dialog(dialog):
            dialog_messages.append(dialog.message)
            dialog.dismiss()

        self.page.on("dialog", handle_dialog)

        land_btn = self.page.query_selector(
            f'.landing-now-btn[data-flight-id="{self.flight.pk}"]'
        )
        assert (
            land_btn is not None
        ), "Land Now button should be present for in-flight glider"

        land_btn.click()
        self.page.wait_for_timeout(600)

        assert (
            len(dialog_messages) > 0
        ), "An alert dialog should appear when the server returns a 500 error"
        msg = dialog_messages[0].lower()
        assert (
            "500" in msg or "could not" in msg or "server error" in msg
        ), f"Alert should describe the server error, got: '{dialog_messages[0]}'"

        # Directly assert the button is NOT in the pending-sync UI state.
        # When landing goes offline-pending, the handler removes btn-warning and
        # adds btn-secondary.  The normal in-flight button stays btn-warning.
        btn_class = land_btn.get_attribute("class") or ""
        assert (
            "btn-secondary" not in btn_class
        ), "Land button should NOT switch to btn-secondary (Pending Sync) on a server error"
        assert (
            "Pending Sync" not in land_btn.inner_text()
        ), f"Land button text should not say 'Pending Sync', got: '{land_btn.inner_text()}'"

    def test_launch_now_session_timeout_shows_alert_not_pending(self):
        """
        Regression test for session-timeout edge case (Issue #707).

        When a session expires, Django redirects to the login page. The fetch()
        follows the redirect and returns a 200 OK HTML login page.
        resp.ok === True but resp.json() throws a SyntaxError.

        If that SyntaxError bubbles to the outer catch it would be treated as a
        network failure and queue the operation as offline-pending.

        The fix narrows the offline-queue path to only fetch() exceptions and
        wraps resp.json() in its own try/catch that alerts instead.
        """
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Simulate a session-timeout redirect: 200 OK but HTML body (not JSON)
        self.page.route(
            f"**/logsheet/flight/{self.flight.pk}/launch_now/",
            lambda route: route.fulfill(
                status=200,
                body="<html><body><h1>Please log in</h1></body></html>",
                content_type="text/html",
            ),
        )

        dialog_messages = []

        def handle_dialog(dialog):
            dialog_messages.append(dialog.message)
            dialog.dismiss()

        self.page.on("dialog", handle_dialog)

        launch_btn = self.page.query_selector(
            f'.launch-now-btn[data-flight-id="{self.flight.pk}"]'
        )
        assert launch_btn is not None

        launch_btn.click()
        self.page.wait_for_timeout(600)

        # An alert should have fired (session timeout message)
        assert len(dialog_messages) > 0, (
            "An alert dialog should appear when the server returns a 200 HTML "
            "page (e.g. session-timeout login redirect) instead of JSON"
        )
        msg = dialog_messages[0].lower()
        assert (
            "refresh" in msg or "unexpected" in msg or "server" in msg
        ), f"Alert should describe the unexpected response, got: '{dialog_messages[0]}'"

        # Must NOT be stuck in Pending Sync state
        btn_text = launch_btn.inner_text()
        assert "Pending Sync" not in btn_text, (
            f"Button should not say 'Pending Sync' after a session-timeout 200 "
            f"HTML response, got: '{btn_text}'"
        )
        btn_class = launch_btn.get_attribute("class") or ""
        assert (
            "btn-warning" not in btn_class
        ), "Launch button should NOT switch to btn-warning on a session-timeout response"

    # ------------------------------------------------------------------
    # Sync Now button: UI appears and triggers sync
    # ------------------------------------------------------------------

    def test_sync_now_button_appears_and_triggers_sync(self):
        """
        When pending offline operations exist, the #offline-sync-status element
        should render a "Sync Now" button.  Clicking it must invoke
        window.M2SSyncPendingFlights (or fall back to dispatching the 'online'
        event), change its label to "Retry", and must NOT open an alert dialog.

        We simulate the pending-indicator state by mocking
        window.M2SIndexedDB.getPendingFlights() to return a non-empty list, then
        calling window.M2SOffline.updatePendingIndicator() to render the button.
        """
        self.page.goto(f"{self.live_server_url}/logsheet/manage/{self.logsheet.pk}/")

        # Wait for the offline bundle to finish loading.
        self.page.wait_for_function(
            "() => window.M2SOffline && typeof window.M2SOffline.updatePendingIndicator === 'function'",
            timeout=5000,
        )

        # Install spies and trigger the pending-sync UI in one evaluate so there
        # are no async races between separate evaluate() calls.
        # - getPendingFlightCount() internally calls window.M2SIndexedDB.getPendingFlights().
        #   We mock that method to return a non-empty array so updatePendingIndicator
        #   renders the Sync Now button without requiring real IndexedDB entries.
        # - M2SSyncPendingFlights is replaced with a spy that records calls.
        # - updatePendingIndicator() is awaited so the DOM is updated before
        #   wait_for_selector() is called.
        self.page.evaluate(
            """async () => {
            window._syncNowCallCount = 0;
            window.M2SSyncPendingFlights = async function() {
                window._syncNowCallCount++;
            };
            // Mock at the IndexedDB layer so the closed-over getPendingFlightCount
            // sees a non-zero count and renders the Sync Now button.
            if (window.M2SIndexedDB) {
                window.M2SIndexedDB.getPendingFlights = async function() {
                    return [{ id: 1, type: 'launch' }];
                };
            }
            await window.M2SOffline.updatePendingIndicator();
        }"""
        )

        # Wait for the button to be injected into the DOM.
        sync_btn = self.page.query_selector("#force-sync-now-btn")
        assert (
            sync_btn is not None
        ), "#force-sync-now-btn should appear when pending items exist"
        assert (
            sync_btn.is_visible()
        ), "Sync Now button should be visible when pending items exist"

        # Clicking it must not show an alert dialog.
        dialog_messages = []

        def capture_dialog(dialog):
            dialog_messages.append(dialog.message)
            dialog.dismiss()

        self.page.on("dialog", capture_dialog)

        sync_btn.click()
        # Give async click handler time to complete.
        self.page.wait_for_timeout(800)

        # The spy should have been called exactly once.
        call_count = self.page.evaluate("() => window._syncNowCallCount")
        assert call_count == 1, (
            f"window.M2SSyncPendingFlights should be called once on Sync Now click, "
            f"got {call_count}"
        )

        # No alert dialogs should have been shown.
        assert (
            len(dialog_messages) == 0
        ), f"Sync Now click should NOT open an alert dialog, got: {dialog_messages}"

        # Button label should have changed to "Retry" after the sync completes.
        btn_text = sync_btn.inner_text()
        assert (
            "Retry" in btn_text
        ), f"Sync Now button should change to 'Retry' after sync, got: '{btn_text}'"

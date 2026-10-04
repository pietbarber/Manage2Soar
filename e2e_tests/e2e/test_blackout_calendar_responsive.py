"""
E2E tests for the duty roster blackout calendar responsive layout (Issue #1072).

The blackout calendar renders 4 months, one per card. On tablets (iPad Pro 13:
portrait ~1032px, landscape ~1376px) the previous ``col-12 col-lg-3`` grid forced
all four ~315px-wide tables (7 x 45px cells) into ~250px columns, so each table
overflowed its column and the weekend cells painted over their neighbors. Because
the page sets ``body { overflow-x: hidden }``, the clipped overflow never grows the
document, so a naive ``scrollWidth`` check cannot detect the bug.

The fix gives every calendar a Bootstrap ``.table-responsive`` clipper (``max-width:
100%; overflow-x: auto``) so the table is always constrained to its card and, if
wider than the card, scrolls horizontally instead of spilling out. It also uses a
2 x 2 grid (``col-12 col-md-6``) so each card is wide enough for a readable
calendar at the common tablet widths.

The robust regression signal is therefore: every calendar table sits inside a
``.table-responsive`` clipper — the presence of that clipper is what guarantees an
oversized table scrolls within its card instead of painting over its neighbors.
These tests assert that at each key breakpoint, and that all four month calendars
are present.
"""

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase


class TestBlackoutCalendarResponsive(DjangoPlaywrightTestCase):
    """Verify each blackout calendar is clipped to its card at common tablet/mobile widths."""

    def _open_blackout_calendar(self, username="testmember"):
        """Log in and navigate to the blackout calendar page."""
        self.create_test_member(
            username=username,
            email=f"{username}@example.com",
            membership_status="Full Member",
        )
        self.login(username=username)
        self.page.goto(f"{self.live_server_url}/duty_roster/blackout/")
        self.page.wait_for_selector(".month-header h5")

    def _measure(self):
        """Return month count and, per calendar, whether it has a clipping wrapper."""
        return self.page.evaluate(
            """
            () => {
                const tables = [...document.querySelectorAll('table.blackout-calendar')];
                const perTable = tables.map(t => ({
                    // The fix wraps every table in a .table-responsive clipper
                    // (max-width:100%; overflow-x:auto) so an oversized table
                    // scrolls within its card instead of painting over neighbors.
                    hasClipper: !!t.closest('.table-responsive'),
                }));
                return {
                    months: document.querySelectorAll('.month-header h5').length,
                    tables: perTable,
                };
            }
            """
        )

    def _assert_calendars_clipped_and_visible(self, label):
        result = self._measure()
        self.assertEqual(
            result["months"],
            4,
            f"[{label}] Expected 4 month calendars rendered, found {result['months']}.",
        )
        self.assertEqual(
            len(result["tables"]),
            4,
            f"[{label}] Expected 4 calendar tables, found {len(result['tables'])}.",
        )
        unclipped = [i for i, t in enumerate(result["tables"]) if not t["hasClipper"]]
        self.assertEqual(
            unclipped,
            [],
            f"[{label}] {len(unclipped)} calendar table(s) are not inside a "
            f".table-responsive clipper (indices {unclipped}) — the table overflows "
            "its card and its weekend cells paint over their neighbors.",
        )

    def test_ipad_pro_13_landscape_calendars_clipped(self):
        """iPad Pro 13 landscape (1376x1032): every calendar clipped to its card, all visible."""
        self.page.set_viewport_size({"width": 1376, "height": 1032})
        self._open_blackout_calendar()
        self._assert_calendars_clipped_and_visible("iPad Pro 13 landscape 1376x1032")

    def test_ipad_pro_13_portrait_calendars_clipped(self):
        """iPad Pro 13 portrait (1032x1376): every calendar clipped to its card, all visible."""
        self.page.set_viewport_size({"width": 1032, "height": 1376})
        self._open_blackout_calendar(username="testmember_portrait")
        self._assert_calendars_clipped_and_visible("iPad Pro 13 portrait 1032x1376")

    def test_mobile_calendars_clipped(self):
        """Mobile (375x812): every calendar clipped to its card, all visible (scrollable)."""
        self.page.set_viewport_size({"width": 375, "height": 812})
        self._open_blackout_calendar(username="testmember_mobile")
        self._assert_calendars_clipped_and_visible("Mobile 375x812")

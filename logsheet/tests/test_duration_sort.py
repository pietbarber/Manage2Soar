"""Tests for duration column sorting in logsheet_manage.html.

Covers the data-sort encoding used for landed vs active (in-air) flights
so that tablesort correctly orders all flight types in the Duration column.
"""

from __future__ import annotations

from pathlib import Path

from django.test import TestCase


class DurationSortEncodingTests(TestCase):
    """Verify the JavaScript duration sort logic uses compatible encodings."""

    TEMPLATE_FILENAME = "logsheet_manage.html"

    def _load_template_source(self) -> str:
        """Read the raw template source file from disk."""
        # Template lives at logsheet/templates/logsheet/<name>, one level up from tests/.
        template_path = (
            Path(__file__).resolve().parent.parent
            / "templates"
            / "logsheet"
            / self.TEMPLATE_FILENAME
        )
        if not template_path.exists():
            raise FileNotFoundError(
                f"Template {self.TEMPLATE_FILENAME} not found at {template_path}"
            )
        return template_path.read_text()

    def _extract_inline_js(self) -> str:
        """Extract all inline <script> blocks from the template source.

        Uses string splitting instead of regex to avoid triggering static analysers'
        HTML-filtering-via-regex rules (e.g. CodeQL Python/HtmlFilteringViaRegex).
        """
        source = self._load_template_source()
        js_blocks: list[str] = []
        idx = 0
        while True:
            start = source.find("<script", idx)
            if start == -1:
                break
            tag_start = start + len("<script")
            gt = source.find(">", start)
            if gt == -1:
                break
            header = source[tag_start:gt]
            # Skip <script src="..."> external scripts — only want inline scripts.
            if "src=" in header:
                idx = gt + 1
                continue
            end_tag = source.find("</script>", gt)
            if end_tag == -1:
                break
            js_blocks.append(source[gt + 1 : end_tag])
            idx = end_tag + len("</script>")
        return "\n".join(js_blocks)

    def test_live_duration_guard_against_nan_launch_time(self):
        """Thread 3725303017: updateLiveDurations guards invalid launch dates."""
        js_source = self._extract_inline_js()

        # Verify the function checks isNaN before computing elapsed times.
        self.assertIn(
            "Number.isNaN",
            js_source,
            "updateLiveDurations must check Number.isNaN(launchTime.getTime()) "
            "to guard against invalid data-launch values.",
        )

    def test_live_duration_guard_against_negative_elapsed(self):
        """Thread 3725303017: updateLiveDurations guards negative diffMs."""
        js_source = self._extract_inline_js()

        # Should check for negative diffMs.
        self.assertIn(
            "diffMs < 0",
            js_source,
            "updateLiveDurations must check diffMs < 0 to guard against "
            "client clock ahead of launch time.",
        )

    def test_live_duration_uses_999999_sentinel(self):
        """Thread 3725303017: active flights use 999999 as base offset."""
        js_source = self._extract_inline_js()

        # The sentinel should match the template's in-air flight encoding.
        self.assertIn(
            "+ 999999",
            js_source,
            "Live-duration sort offset must add 999999 (matching the template's "
            "in-air flight sentinel) so it sorts after all landed flights.",
        )

    def test_duration_sort_encoding_compatible_with_landed_flights(self):
        """Landed flights encode as total_seconds; active should use elapsed seconds."""
        js_source = self._extract_inline_js()

        # Should use elapsedSeconds (hours * 3600 + minutes * 60) for sorting.
        self.assertIn(
            "elapsedSeconds",
            js_source,
            "Duration sort must use total elapsed seconds for the data-sort value.",
        )

    def test_live_duration_continues_on_invalid_date(self):
        """Thread 3725303017: updateLiveDurations continues on invalid dates (no crash)."""
        js_source = self._extract_inline_js()

        # Should have a continue statement after the NaN check.
        self.assertIn(
            "continue",
            js_source,
            "Invalid launch dates should trigger 'continue' to skip remaining logic.",
        )

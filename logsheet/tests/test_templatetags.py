"""Tests for logsheet template filters (logsheet_tags.py)."""

from datetime import time, timedelta

import pytest

from logsheet.templatetags.logsheet_tags import bs_tag, format_duration

# =============================================================================
# format_duration
# =============================================================================


class TestFormatDuration:
    def test_none_returns_empty_string(self):
        assert format_duration(None) == ""

    def test_zero_duration(self):
        assert format_duration(timedelta(0)) == "0:00"

    def test_minutes_only(self):
        assert format_duration(timedelta(minutes=23)) == "0:23"

    def test_hours_and_minutes(self):
        assert format_duration(timedelta(hours=1, minutes=5)) == "1:05"

    def test_minutes_padded_to_two_digits(self):
        assert format_duration(timedelta(hours=2, minutes=7)) == "2:07"

    def test_multi_hour_flight(self):
        assert format_duration(timedelta(hours=3, minutes=45)) == "3:45"

    def test_negative_timedelta_returns_empty_string(self):
        assert format_duration(timedelta(seconds=-1)) == ""

    def test_non_timedelta_returns_str_of_value(self):
        # Should fall back gracefully for unexpected types
        assert format_duration("oops") == "oops"
        assert format_duration(42) == "42"

    def test_exactly_one_hour(self):
        assert format_duration(timedelta(hours=1)) == "1:00"

    def test_whole_minutes_no_remainder(self):
        # 90 minutes = 1 h 30 min
        assert format_duration(timedelta(minutes=90)) == "1:30"


# =============================================================================
# bs_tag
# =============================================================================


class TestBsTag:
    def test_debug_maps_to_secondary(self):
        assert bs_tag("debug") == "secondary"

    def test_danger_passes_through(self):
        assert bs_tag("danger") == "danger"

    def test_success_passes_through(self):
        assert bs_tag("success") == "success"

    def test_warning_passes_through(self):
        assert bs_tag("warning") == "warning"

    def test_info_passes_through(self):
        assert bs_tag("info") == "info"

    def test_unknown_tag_passes_through(self):
        assert bs_tag("primary") == "primary"

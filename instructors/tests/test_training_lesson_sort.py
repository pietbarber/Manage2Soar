"""Tests for TrainingLesson sort_key functionality (Issue #574)."""

import pytest
from django.test import TestCase

from instructors.models import TrainingLesson, generate_sort_key


class TestGenerateSortKey(TestCase):
    """Test the generate_sort_key function for natural/version number sorting."""

    def test_simple_integers(self):
        """Simple integer codes should be zero-padded."""
        assert generate_sort_key("1") == "00001"
        assert generate_sort_key("10") == "00010"
        assert generate_sort_key("100") == "00100"

    def test_nested_version_numbers(self):
        """Nested version numbers (1.10) should sort correctly."""
        # Key insight: 1.2 should sort BEFORE 1.10
        key_1_2 = generate_sort_key("1.2")
        key_1_10 = generate_sort_key("1.10")
        assert key_1_2 < key_1_10, f"Expected {key_1_2} < {key_1_10}"

    def test_version_number_format(self):
        """Verify exact format of version number sort keys."""
        assert generate_sort_key("1.1") == "00001.00001"
        assert generate_sort_key("1.10") == "00001.00010"
        assert generate_sort_key("2.0") == "00002.00000"
        assert generate_sort_key("10.5") == "00010.00005"

    def test_alphanumeric_codes(self):
        """Codes with letters (e.g., '2a') should preserve the suffix."""
        assert generate_sort_key("2a") == "00002a"
        assert generate_sort_key("10b") == "00010b"

    def test_mixed_codes(self):
        """Test various code formats that might appear in syllabi."""
        # Simple numeric
        assert generate_sort_key("5") == "00005"
        # Alphanumeric
        assert generate_sort_key("2l") == "00002l"
        # Version format
        assert generate_sort_key("3.14") == "00003.00014"

    def test_sort_order_comprehensive(self):
        """Verify that a list of codes sorts in the expected order."""
        codes = ["1.1", "1.10", "1.11", "1.2", "1.3", "1.9", "2.0", "2.1", "10.0"]
        expected_order = [
            "1.1",
            "1.2",
            "1.3",
            "1.9",
            "1.10",
            "1.11",
            "2.0",
            "2.1",
            "10.0",
        ]

        # Sort by sort_key
        sorted_codes = sorted(codes, key=generate_sort_key)
        assert (
            sorted_codes == expected_order
        ), f"Got {sorted_codes}, expected {expected_order}"


class TestTrainingLessonSortKey(TestCase):
    """Test that TrainingLesson model correctly uses sort_key for ordering."""

    def test_sort_key_auto_generated_on_save(self):
        """sort_key should be auto-generated when saving a TrainingLesson."""
        lesson = TrainingLesson.objects.create(
            code="1.10",
            title="Test Lesson 1.10",
        )
        lesson.refresh_from_db()
        assert lesson.sort_key == "00001.00010"

    def test_lessons_ordered_by_sort_key(self):
        """TrainingLesson queryset should be ordered by sort_key (natural order)."""
        # Create lessons in "wrong" order
        TrainingLesson.objects.create(code="1.10", title="Lesson 1.10")
        TrainingLesson.objects.create(code="1.2", title="Lesson 1.2")
        TrainingLesson.objects.create(code="1.1", title="Lesson 1.1")
        TrainingLesson.objects.create(code="2.0", title="Lesson 2.0")

        # Fetch with default ordering (should be by sort_key)
        codes = list(TrainingLesson.objects.values_list("code", flat=True))
        assert codes == ["1.1", "1.2", "1.10", "2.0"], f"Got {codes}"

    def test_sort_key_updated_on_code_change(self):
        """If code changes, sort_key should update on save."""
        lesson = TrainingLesson.objects.create(code="1.5", title="Test")
        assert lesson.sort_key == "00001.00005"

        lesson.code = "2.15"
        lesson.save()
        lesson.refresh_from_db()
        assert lesson.sort_key == "00002.00015"

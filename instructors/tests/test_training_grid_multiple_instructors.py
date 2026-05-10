"""
Tests for member_training_grid view with multiple instructors.

Issue #903: Training Grid showed incorrect flight totals when multiple
instructors flew with the same student on the same day. The grid would
show the combined flight count next to the first instructor's name.
"""

from datetime import timedelta

import pytest
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from instructors.models import InstructionReport, LessonScore, TrainingLesson
from logsheet.models import Airfield, Flight, Glider, Logsheet, Towplane
from members.models import Member


@pytest.mark.django_db
class TestTrainingGridMultipleInstructors(TestCase):
    """Tests for training_grid view with multiple instructors on same day."""

    @classmethod
    def setUpTestData(cls):
        """Create test data with two instructors flying on same day."""
        # Create student
        cls.student = Member.objects.create(
            username="student",
            first_name="Test",
            last_name="Student",
            email="student@example.com",
            membership_status="Full Member",
        )

        # Create two instructors
        cls.instructor1 = Member.objects.create(
            username="instructor1",
            first_name="Manny",
            last_name="Serrano",
            email="manny@example.com",
            membership_status="Full Member",
            instructor=True,
        )
        cls.instructor2 = Member.objects.create(
            username="instructor2",
            first_name="Rufus",
            last_name="Decker",
            email="rufus@example.com",
            membership_status="Full Member",
            instructor=True,
        )

        # Create test glider
        cls.glider = Glider.objects.create(
            n_number="N12345",
            make="Test",
            model="GliderTest",
            club_owned=True,
            is_active=True,
        )

        # Create towplane
        cls.towplane = Towplane.objects.create(
            n_number="N99999",
            make="Test",
            model="Tow",
            club_owned=True,
            is_active=True,
        )

        # Create airfield
        cls.airfield = Airfield.objects.create(name="Test Field", identifier="KXYZ")

        # Create a logsheet for a specific date
        cls.log_date = timezone.now().date()
        cls.logsheet = Logsheet.objects.create(
            log_date=cls.log_date,
            airfield=cls.airfield,
            created_by=cls.student,
            finalized=True,
        )

        # Create 2 flights with instructor 1, 1 flight with instructor 2 on the same day
        # (simulating the issue scenario: "I flew two flights with Manny, Rufus flew with him once")
        for _ in range(2):
            Flight.objects.create(
                logsheet=cls.logsheet,
                pilot=cls.student,
                glider=cls.glider,
                towplane=cls.towplane,
                instructor=cls.instructor1,
            )

        Flight.objects.create(
            logsheet=cls.logsheet,
            pilot=cls.student,
            glider=cls.glider,
            towplane=cls.towplane,
            instructor=cls.instructor2,
        )

        # Create instruction report for only the first instructor on this date
        # (This is the actual issue scenario: flights from multiple instructors,
        # but only one instruction report filed)
        InstructionReport.objects.create(
            student=cls.student,
            instructor=cls.instructor1,
            report_date=cls.log_date,
        )

        # Create a dummy training lesson
        cls.lesson = TrainingLesson.objects.create(
            code="1.1",
            title="Fundamentals",
        )

    def setUp(self):
        """Set up for each test."""
        self.client = Client()

    def test_training_grid_shows_correct_instructor_flight_counts(self):
        """
        Verify that the training grid shows correct flight counts per instructor
        when multiple instructors fly on the same day.

        Expected: Instructor 1 (Manny) should show 2 flights, Instructor 2 (Rufus)
        should show 1 flight, NOT 3 flights each.
        """
        # Login as student
        self.client.force_login(self.student)

        # Access the training grid
        url = reverse("instructors:member_training_grid", args=[self.student.id])
        response = self.client.get(url)

        assert response.status_code == 200, "Training grid should be accessible"

        # Get column_metadata from context
        column_metadata = response.context.get("column_metadata", [])
        assert len(column_metadata) > 0, "Column metadata should exist"

        # Find the column for our date
        date_columns = [m for m in column_metadata if m["date"] == self.log_date]
        assert len(date_columns) == 1, "Should have exactly one column for our date"

        column = date_columns[0]

        # The column should show the first instructor's flight count (2, not 3)
        # This is the key fix: it should only count flights for that specific instructor
        assert (
            column["num_flights"] == 2
        ), f"First instructor column should show 2 flights, got {column['num_flights']}"
        assert (
            column["instructor_name"] == "Manny Serrano"
        ), f"Column should show Manny Serrano, got {column['instructor_name']}"

    def test_training_grid_instructor_initials_correct(self):
        """Verify that instructor initials are correctly displayed."""
        self.client.force_login(self.student)
        url = reverse("instructors:member_training_grid", args=[self.student.id])
        response = self.client.get(url)

        column_metadata = response.context.get("column_metadata", [])
        date_columns = [m for m in column_metadata if m["date"] == self.log_date]
        column = date_columns[0]

        # Verify initials match the first instructor (Manny Serrano -> MS)
        assert column["initials"] == "MS", f"Expected 'MS', got {column['initials']}"

    def test_training_grid_flights_tooltip_shows_correct_instructor_flights(self):
        """Verify that the tooltip shows flights for the correct instructor."""
        self.client.force_login(self.student)
        url = reverse("instructors:member_training_grid", args=[self.student.id])
        response = self.client.get(url)

        column_metadata = response.context.get("column_metadata", [])
        date_columns = [m for m in column_metadata if m["date"] == self.log_date]
        column = date_columns[0]

        # The tooltip should indicate 2 flights (not 3)
        tooltip = column["flights_tooltip"]
        assert (
            "2 flights" in tooltip
        ), f"Tooltip should mention '2 flights' for this instructor, got: {tooltip}"

    def test_training_grid_single_instructor_unchanged(self):
        """Verify that single-instructor flights still work correctly (regression test)."""
        # Create another guaranteed-past date with only instructor 1
        log_date_2 = self.log_date - timedelta(days=1)
        logsheet_2 = Logsheet.objects.create(
            log_date=log_date_2,
            airfield=self.airfield,
            created_by=self.student,
            finalized=True,
        )

        # 3 flights with only instructor 1
        for _ in range(3):
            Flight.objects.create(
                logsheet=logsheet_2,
                pilot=self.student,
                glider=self.glider,
                towplane=self.towplane,
                instructor=self.instructor1,
            )

        InstructionReport.objects.create(
            student=self.student,
            instructor=self.instructor1,
            report_date=log_date_2,
        )

        self.client.force_login(self.student)
        url = reverse("instructors:member_training_grid", args=[self.student.id])
        response = self.client.get(url)

        column_metadata = response.context.get("column_metadata", [])
        date_columns = [m for m in column_metadata if m["date"] == log_date_2]

        assert len(date_columns) == 1, "Should have one column for the new date"
        column = date_columns[0]

        assert (
            column["num_flights"] == 3
        ), f"Should show 3 flights, got {column['num_flights']}"
        assert "3 flights" in column["flights_tooltip"]

    def test_training_grid_same_date_multiple_reports_use_report_instructor(self):
        """Verify each same-date report column uses that report's instructor and score."""
        report_1 = InstructionReport.objects.get(
            student=self.student,
            instructor=self.instructor1,
            report_date=self.log_date,
        )
        report_2 = InstructionReport.objects.create(
            student=self.student,
            instructor=self.instructor2,
            report_date=self.log_date,
        )

        LessonScore.objects.create(report=report_1, lesson=self.lesson, score="2")
        LessonScore.objects.create(report=report_2, lesson=self.lesson, score="4")

        self.client.force_login(self.student)
        url = reverse("instructors:member_training_grid", args=[self.student.id])
        response = self.client.get(url)

        assert response.status_code == 200

        column_metadata = response.context.get("column_metadata", [])
        same_day_columns = [m for m in column_metadata if m["date"] == self.log_date]
        assert len(same_day_columns) == 2, "Expected two columns for same-day reports"

        first_col = same_day_columns[0]
        second_col = same_day_columns[1]

        assert first_col["instructor_name"] == "Manny Serrano"
        assert first_col["num_flights"] == 2
        assert "2 flights" in first_col["flights_tooltip"]

        assert second_col["instructor_name"] == "Rufus Decker"
        assert second_col["num_flights"] == 1
        assert "1 flight" in second_col["flights_tooltip"]

        lesson_data = response.context.get("lesson_data", [])
        lesson_row = next(
            (r for r in lesson_data if r["lesson_id"] == self.lesson.id), None
        )
        assert lesson_row is not None
        assert [c["score"] for c in lesson_row["scores"]] == ["2", "4"]

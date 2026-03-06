from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from instructors.models import (
    GroundInstruction,
    GroundLessonScore,
    InstructionReport,
    LessonScore,
    TrainingLesson,
    TrainingPhase,
)
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
class TestMemberInstructionRecordDailyDedup:
    def setup_method(self):
        MembershipStatus.objects.update_or_create(
            name="Full Member", defaults={"is_active": True}
        )

        self.student = Member.objects.create_user(
            username="instruction_student",
            password="testpass123",
            first_name="Student",
            last_name="Pilot",
            membership_status="Full Member",
            is_active=True,
        )
        self.instructor = Member.objects.create_user(
            username="instruction_cfi",
            password="testpass123",
            first_name="Casey",
            last_name="Instructor",
            membership_status="Full Member",
            is_active=True,
            instructor=True,
        )

        phase = TrainingPhase.objects.create(number=1, name="Phase 1")
        self.lesson_a = TrainingLesson.objects.create(
            code="1.1",
            title="Intro Pattern",
            phase=phase,
        )
        self.lesson_b = TrainingLesson.objects.create(
            code="1.2",
            title="Crosswind",
            phase=phase,
        )

    def test_daily_syllabus_items_are_deduplicated_and_keep_best_score(self, client):
        report_date = timezone.localdate() - timedelta(days=2)

        report = InstructionReport.objects.create(
            student=self.student,
            instructor=self.instructor,
            report_date=report_date,
        )
        LessonScore.objects.create(report=report, lesson=self.lesson_a, score="2")
        LessonScore.objects.create(report=report, lesson=self.lesson_b, score="3")

        ground = GroundInstruction.objects.create(
            student=self.student,
            instructor=self.instructor,
            date=report_date,
            location="Clubhouse",
        )
        # Same lesson appears again at a better score on the same day.
        GroundLessonScore.objects.create(
            session=ground, lesson=self.lesson_a, score="3"
        )
        # Duplicate lesson/score should not duplicate links in the daily summary.
        GroundLessonScore.objects.create(
            session=ground, lesson=self.lesson_b, score="3"
        )

        client.force_login(self.student)
        response = client.get(
            reverse("instructors:member_instruction_record", args=[self.student.pk])
        )

        assert response.status_code == 200
        daily_blocks = response.context["daily_blocks"]
        assert len(daily_blocks) == 1

        score_groups = daily_blocks[0]["syllabus_score_groups"]
        groups_by_score = {group["score"]: group["lessons"] for group in score_groups}

        assert "2" not in groups_by_score
        solo_codes = [lesson["code"] for lesson in groups_by_score["3"]]
        assert sorted(solo_codes) == ["1.1", "1.2"]

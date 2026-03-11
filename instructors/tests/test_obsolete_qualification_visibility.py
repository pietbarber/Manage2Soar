from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from instructors.models import (
    ClubQualificationType,
    MemberQualification,
    TrainingLesson,
)
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
class TestInstructorQualificationVisibility:
    def setup_method(self):
        MembershipStatus.objects.update_or_create(
            name="Full Member", defaults={"is_active": True}
        )

        self.instructor = Member.objects.create_user(
            username="qual_instructor",
            password="testpass123",
            first_name="Inst",
            last_name="Ructor",
            membership_status="Full Member",
            is_active=True,
            instructor=True,
        )
        self.student = Member.objects.create_user(
            username="qual_student",
            password="testpass123",
            first_name="Stu",
            last_name="Dent",
            membership_status="Full Member",
            is_active=True,
        )

        TrainingLesson.objects.create(code="1.1", title="Basic", sort_key="00001.00001")

        self.active_non_obsolete = ClubQualificationType.objects.create(
            code="SAFE2026",
            name="Safety Meeting 2026",
            is_obsolete=False,
        )
        self.inactive_non_obsolete = ClubQualificationType.objects.create(
            code="SAFE2024",
            name="Safety Meeting 2024",
            is_obsolete=False,
        )
        self.obsolete = ClubQualificationType.objects.create(
            code="SAFE2023",
            name="Safety Meeting 2023",
            is_obsolete=True,
        )

        MemberQualification.objects.create(
            member=self.student,
            qualification=self.active_non_obsolete,
            is_qualified=True,
            date_awarded=date.today(),
        )
        MemberQualification.objects.create(
            member=self.student,
            qualification=self.inactive_non_obsolete,
            is_qualified=False,
            date_awarded=date.today(),
        )
        MemberQualification.objects.create(
            member=self.student,
            qualification=self.obsolete,
            is_qualified=True,
            date_awarded=date.today(),
        )

    def test_fill_instruction_report_shows_inactive_non_obsolete(self, client):
        client.force_login(self.instructor)
        url = reverse(
            "instructors:fill_instruction_report",
            args=[self.student.id, timezone.localdate().strftime("%Y-%m-%d")],
        )

        response = client.get(url)

        assert response.status_code == 200
        quals = list(response.context["existing_qualifications"])
        codes = {q.qualification.code for q in quals}
        assert "SAFE2026" in codes
        assert "SAFE2024" in codes
        assert "SAFE2023" not in codes

    def test_log_ground_instruction_shows_inactive_non_obsolete(self, client):
        client.force_login(self.instructor)
        url = reverse("instructors:log_ground_instruction")

        response = client.get(url, {"student_id": self.student.id})

        assert response.status_code == 200
        quals = list(response.context["existing_qualifications"])
        codes = {q.qualification.code for q in quals}
        assert "SAFE2026" in codes
        assert "SAFE2024" in codes
        assert "SAFE2023" not in codes

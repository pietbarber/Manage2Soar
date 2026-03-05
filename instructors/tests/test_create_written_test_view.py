import pytest
from django.test import TestCase
from django.urls import reverse

from knowledgetest.models import QuestionCategory
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
class TestCreateWrittenTestView(TestCase):
    @classmethod
    def setUpTestData(cls):
        MembershipStatus.objects.get_or_create(
            name="Full Member", defaults={"is_active": True}
        )

        cls.instructor = Member.objects.create_user(
            username="instructor_ctv",
            first_name="Test",
            last_name="Instructor",
            email="instructor_ctv@example.com",
            password="testpass123",
            membership_status="Full Member",
            instructor=True,
        )
        cls.student = Member.objects.create_user(
            username="student_ctv",
            first_name="Test",
            last_name="Student",
            email="student_ctv@example.com",
            password="testpass123",
            membership_status="Full Member",
        )
        cls.url = reverse("instructors:create-written-test")

    def test_get_includes_weight_fields_and_weight_inputs_when_categories_exist(self):
        QuestionCategory.objects.create(code="GF", description="Ground Fundamentals")
        QuestionCategory.objects.create(code="WX", description="Weather")

        self.client.force_login(self.instructor)
        response = self.client.get(self.url)

        assert response.status_code == 200
        assert "weight_fields" in response.context

        weight_field_names = [field.name for field in response.context["weight_fields"]]
        assert weight_field_names == ["weight_GF", "weight_WX"]

        content = response.content.decode("utf-8")
        assert 'name="weight_GF"' in content
        assert 'name="weight_WX"' in content

    def test_get_shows_empty_state_when_no_categories_exist(self):
        self.client.force_login(self.instructor)
        response = self.client.get(self.url)

        assert response.status_code == 200
        assert "weight_fields" in response.context
        assert list(response.context["weight_fields"]) == []
        assert b"No question categories are configured yet." in response.content

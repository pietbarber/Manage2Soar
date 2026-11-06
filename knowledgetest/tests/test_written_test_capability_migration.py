"""Regression tests for written-test capability migration ordering."""

import pytest
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.urls import reverse

from knowledgetest.models import Question, QuestionCategory, WrittenTestTemplate
from members.models import Member
from siteconfig.models import MembershipStatus

WRITTEN_TEST_CAPABILITIES = {
    "start_unassigned_written_test",
    "delete_any_written_test_attempt",
    "view_recent_written_tests",
    "delete_any_pending_written_test_assignment",
}


def _instructor_admin_capabilities():
    group = Group.objects.get(name="Instructor Admins")
    return (
        set(
            group.permissions.filter(
                content_type__app_label="knowledgetest"
            ).values_list("codename", flat=True)
        )
        & WRITTEN_TEST_CAPABILITIES
    )


@pytest.mark.django_db(transaction=True)
def test_fresh_migration_creates_and_grants_all_written_test_capabilities():
    """0008 repairs the grant when 0007 ran before post_migrate permissions."""
    executor = MigrationExecutor(connection)
    leaf_targets = executor.loader.graph.leaf_nodes()
    before = ("knowledgetest", "0007_grant_written_test_capabilities")
    after = (
        "knowledgetest",
        "0008_create_and_grant_written_test_capabilities",
    )

    try:
        executor.migrate([before])
        Permission.objects.filter(
            content_type__app_label="knowledgetest",
            codename__in=WRITTEN_TEST_CAPABILITIES,
        ).delete()

        MigrationExecutor(connection).migrate([after])

        assert _instructor_admin_capabilities() == WRITTEN_TEST_CAPABILITIES
        assert Permission.objects.filter(
            content_type__app_label="knowledgetest",
            codename__in=WRITTEN_TEST_CAPABILITIES,
        ).count() == len(WRITTEN_TEST_CAPABILITIES)
    finally:
        MigrationExecutor(connection).migrate(leaf_targets)


@pytest.mark.django_db
def test_instructor_admin_can_start_unassigned_written_test_after_migration(client):
    """The migrated group grant enables the actual instructor-facing flow."""
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    instructor = Member.objects.create_user(
        username="fresh-written-test-instructor",
        password="password",
        membership_status="Full Member",
    )
    instructor.groups.add(Group.objects.get(name="Instructor Admins"))

    category = QuestionCategory.objects.create(code="FRESH", description="Fresh")
    question = Question.objects.create(
        qnum=9901,
        category=category,
        question_text="Fresh-install question?",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        correct_answer="A",
    )
    template = WrittenTestTemplate.objects.create(name="Fresh-install test")
    template.questions.add(question, through_defaults={"order": 1})

    client.force_login(instructor)
    response = client.get(reverse("knowledgetest:quiz-start", args=[template.pk]))

    assert response.status_code == 200

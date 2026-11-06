import pytest
from django.contrib.auth.models import Permission
from django.test import RequestFactory

from members.context_processors import authorization
from members.models import Member
from siteconfig.models import MembershipStatus


def _request_for(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


def _grant_permission(user, *, app_label, codename):
    user.user_permissions.add(
        Permission.objects.get(
            content_type__app_label=app_label,
            codename=codename,
        )
    )


@pytest.mark.django_db
def test_billing_navigation_context_requires_active_membership(db):
    inactive_status = MembershipStatus.objects.create(
        name="Inactive Context Member", is_active=False
    )
    treasurer = Member.objects.create_user(
        username="inactive-context-treasurer",
        treasurer=True,
        membership_status=inactive_status.name,
    )
    Member.objects.filter(pk=treasurer.pk).update(is_active=True)
    treasurer.refresh_from_db()

    context = authorization(_request_for(treasurer))

    assert context["role_access"]["billing"] is False


@pytest.mark.django_db
def test_billing_navigation_context_preserves_authorized_active_member(db):
    treasurer = Member.objects.create_user(
        username="active-context-treasurer",
        membership_status="Full Member",
    )
    _grant_permission(treasurer, app_label="billing", codename="can_manage_billing")

    context = authorization(_request_for(treasurer))

    assert context["role_access"]["billing"] is True


@pytest.mark.django_db
def test_stats_dump_navigation_context_matches_view_superuser_gate(db):
    superuser = Member.objects.create_superuser(
        username="stats-context-superuser",
        password="pass",
        membership_status="Non-Member",
    )

    context = authorization(_request_for(superuser))

    assert context["role_access"]["stats_dump_export"] is True


@pytest.mark.django_db
def test_stats_dump_navigation_context_preserves_authorized_active_member(db):
    member = Member.objects.create_user(
        username="active-stats-context-member",
        membership_status="Full Member",
    )
    _grant_permission(member, app_label="logsheet", codename="can_export_stats_dump")

    context = authorization(_request_for(member))

    assert context["role_access"]["stats_dump_export"] is True


@pytest.mark.django_db
def test_stats_dump_navigation_context_requires_active_membership(db):
    inactive_status = MembershipStatus.objects.create(
        name="Inactive Stats Context Member", is_active=False
    )
    member = Member.objects.create_user(
        username="inactive-stats-context-member",
        membership_status=inactive_status.name,
    )
    _grant_permission(member, app_label="logsheet", codename="can_export_stats_dump")
    Member.objects.filter(pk=member.pk).update(is_active=True)
    member.refresh_from_db()

    context = authorization(_request_for(member))

    assert context["role_access"]["stats_dump_export"] is False

"""Endpoint-level baseline for legacy membership application access rules."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from members.models import Member
from members.models_applications import MembershipApplication
from members.utils.membership import clear_active_membership_statuses_cache
from siteconfig.models import MembershipStatus


@pytest.fixture
def application(db):
    return MembershipApplication.objects.create(
        first_name="Access",
        last_name="Applicant",
        email="access-applicant@example.com",
        phone="555-123-4567",
        address_line1="123 Main St",
        city="Anytown",
        state="CA",
        zip_code="12345",
        agrees_to_terms=True,
        agrees_to_safety_rules=True,
        agrees_to_financial_obligations=True,
    )


@pytest.fixture
def actor(db):
    MembershipStatus.objects.update_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    MembershipStatus.objects.update_or_create(
        name="Inactive Member", defaults={"is_active": False}
    )
    MembershipStatus.objects.update_or_create(
        name="Role Account", defaults={"is_active": False}
    )
    clear_active_membership_statuses_cache()

    def create(role):
        if role == "anonymous":
            return None
        options = {
            "membership_status": "Full Member",
            "email": f"access-{role}@example.com",
        }
        if role in {"director", "member_manager", "webmaster"}:
            options[role] = True
        elif role == "superuser":
            options["is_superuser"] = True
        elif role == "staff_only":
            options["is_staff"] = True
        elif role == "inactive_manager":
            options.update(membership_status="Inactive Member", member_manager=True)
        elif role == "kiosk":
            options["membership_status"] = "Role Account"
        elif role == "kiosk_manager":
            options.update(membership_status="Role Account", member_manager=True)
        member = Member.objects.create_user(username=f"access-{role}", **options)
        if role == "group_only":
            group, _ = Group.objects.get_or_create(name="Member Managers")
            member.groups.add(group)
        if role in {"kiosk", "kiosk_manager"}:
            # A kiosk role account is login-enabled despite inactive membership.
            Member.objects.filter(pk=member.pk).update(is_active=True)
            member.refresh_from_db()
        return member

    return create


def _login(client, actor, role):
    member = actor(role)
    if member is not None:
        client.force_login(member)
    if role in {"kiosk", "kiosk_manager"}:
        session = client.session
        session["is_kiosk_authenticated"] = True
        session.save()
    return member


def _url(endpoint, application):
    if endpoint == "detail":
        return reverse(
            "members:membership_application_detail", args=[application.application_id]
        )
    return reverse(
        "members:membership_applications_list"
        if endpoint == "list"
        else "members:membership_waitlist"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["list", "detail", "waitlist"])
@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("ordinary", 403),
        ("director", 200),
        ("member_manager", 200),
        ("webmaster", 200),
        ("superuser", 200),
        ("staff_only", 403),
        ("group_only", 403),
        ("anonymous", 302),
        ("inactive_manager", 302),
        ("kiosk", 403),
        ("kiosk_manager", 403),
    ],
)
def test_management_get_access(client, actor, application, role, expected, endpoint):
    _login(client, actor, role)

    response = client.get(_url(endpoint, application))

    assert response.status_code == expected
    if expected == 302:
        assert "login" in response.url
    elif expected == 200:
        assert response.context["can_modify"] is (role != "director")


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint", ["detail", "waitlist"])
@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("ordinary", 403),
        ("director", 403),
        ("staff_only", 403),
        ("group_only", 403),
        ("anonymous", 302),
        ("inactive_manager", 302),
        ("kiosk", 403),
        ("kiosk_manager", 403),
    ],
)
def test_denied_post_does_not_change_application(
    client, actor, application, role, expected, endpoint
):
    application.status = "waitlisted"
    application.waitlist_position = 2
    application.admin_notes = "Original notes"
    application.save()
    first = MembershipApplication.objects.create(
        first_name="First",
        last_name="Applicant",
        email="first-denied@example.com",
        status="waitlisted",
        waitlist_position=1,
    )
    _login(client, actor, role)
    data = (
        {"review_action": "save_notes", "admin_notes": "Unauthorized edit"}
        if endpoint == "detail"
        else {
            "action": "move_to_top",
            "application_id": str(application.application_id),
        }
    )

    response = client.post(_url(endpoint, application), data)

    assert response.status_code == expected
    if expected == 302:
        assert "login" in response.url
    application.refresh_from_db()
    assert application.status == "waitlisted"
    assert application.waitlist_position == 2
    assert application.admin_notes == "Original notes"
    assert application.reviewed_by_id is None
    first.refresh_from_db()
    assert first.waitlist_position == 1


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["member_manager", "webmaster", "superuser"])
def test_authorized_reviewer_can_save_notes(client, actor, application, role):
    _login(client, actor, role)

    response = client.post(
        _url("detail", application),
        {"review_action": "save_notes", "admin_notes": "Reviewed"},
    )

    assert response.status_code == 302
    assert response.url == _url("detail", application)
    application.refresh_from_db()
    assert application.admin_notes == "Reviewed"


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["member_manager", "webmaster", "superuser"])
def test_authorized_reviewer_can_reorder_waitlist(client, actor, application, role):
    application.status = "waitlisted"
    application.waitlist_position = 2
    application.save()
    first = MembershipApplication.objects.create(
        first_name="First",
        last_name="Applicant",
        email="first-applicant@example.com",
        status="waitlisted",
        waitlist_position=1,
    )
    _login(client, actor, role)

    response = client.post(
        _url("waitlist", application),
        {"action": "move_to_top", "application_id": str(application.application_id)},
    )

    assert response.status_code == 302
    assert response.url == _url("waitlist", application)
    application.refresh_from_db()
    first.refresh_from_db()
    assert (application.waitlist_position, first.waitlist_position) == (1, 2)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "expected"),
    [("ordinary", 403), ("director", 200), ("member_manager", 200), ("anonymous", 302)],
)
def test_list_post_uses_same_read_gate_as_get(
    client, actor, application, role, expected
):
    _login(client, actor, role)

    response = client.post(_url("list", application), {"review_action": "reject"})

    assert response.status_code == expected
    if expected == 200:
        assert response.context["can_modify"] is (role != "director")
    application.refresh_from_db()
    assert application.status == "pending"


@pytest.mark.django_db
def test_kiosk_session_with_manager_flag_cannot_read_or_modify_application(
    client, actor, application
):
    """Shared kiosk accounts must not manage private applications."""
    _login(client, actor, "kiosk_manager")

    response = client.get(_url("detail", application))

    assert response.status_code == 403

    response = client.post(
        _url("detail", application),
        {"review_action": "save_notes", "admin_notes": "Kiosk notes"},
    )
    assert response.status_code == 403
    application.refresh_from_db()
    assert application.admin_notes != "Kiosk notes"

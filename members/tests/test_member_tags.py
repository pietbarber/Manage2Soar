import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse

from members.models import MemberTag, MemberTagAssignment
from siteconfig.models import MailingList, MembershipStatus


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(
        username="member-tag-superuser", password="password"
    )


@pytest.fixture
def staff_user(db):
    MembershipStatus.objects.get_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    user = get_user_model().objects.create_user(
        username="member-tag-staff",
        password="password",
        is_staff=True,
        membership_status="Full Member",
    )
    get_user_model().objects.filter(pk=user.pk).update(is_active=True)
    return user


@pytest.mark.django_db
def test_member_tag_is_permissionless_and_has_stable_ordering():
    later = MemberTag.objects.create(key="later", display_label="Later", sort_order=20)
    first = MemberTag.objects.create(key="first", display_label="First", sort_order=10)

    assert list(MemberTag.objects.all()) == [first, later]
    assert MemberTag._meta.default_permissions == ()
    assert MemberTagAssignment._meta.default_permissions == ()


@pytest.mark.django_db
def test_tag_models_create_no_permissions():
    content_types = Permission.objects.filter(
        content_type__app_label="members",
        content_type__model__in=("membertag", "membertagassignment"),
    )
    assert not content_types.exists()


@pytest.mark.django_db
def test_assigning_tag_does_not_change_group_membership_or_permissions():
    member = get_user_model().objects.create_user(username="tagged-member")
    group = Group.objects.create(name="Unrelated group")
    permission = Permission.objects.order_by("pk").first()
    assert permission is not None
    member.groups.add(group)
    group.permissions.add(permission)
    before_groups = set(member.groups.values_list("pk", flat=True))
    before_permissions = set(member.get_group_permissions())
    tag = MemberTag.objects.create(key="volunteer", display_label="Volunteer")

    tag.members.add(member)

    member.refresh_from_db()
    assert MemberTagAssignment.objects.filter(tag=tag, member=member).exists()
    assert set(member.groups.values_list("pk", flat=True)) == before_groups
    assert member.get_group_permissions() == before_permissions


@pytest.mark.django_db
def test_tag_admin_is_superuser_only_and_assigns_members(client, superuser, staff_user):
    add_url = reverse("admin:members_membertag_add")
    client.force_login(staff_user)
    assert client.get(add_url).status_code == 403

    member = get_user_model().objects.create_user(
        username="assignable-member", first_name="Assign", last_name="Me"
    )
    client.force_login(superuser)
    response = client.post(
        add_url,
        {
            "key": "safety-team",
            "display_label": "Safety Team",
            "description": "Manual label",
            "sort_order": "5",
            "is_active": "on",
            "assignments-TOTAL_FORMS": "1",
            "assignments-INITIAL_FORMS": "0",
            "assignments-MIN_NUM_FORMS": "0",
            "assignments-MAX_NUM_FORMS": "1000",
            "assignments-0-member": str(member.pk),
        },
    )

    assert response.status_code == 302
    tag = MemberTag.objects.get(key="safety-team")
    assert tag.members.get() == member


@pytest.mark.django_db
def test_referenced_tag_cannot_be_deleted_through_admin(client, superuser):
    tag = MemberTag.objects.create(key="referenced", display_label="Referenced")
    MailingList.objects.create(name="referenced-tag-list", criteria=[f"tag:{tag.key}"])
    client.force_login(superuser)

    response = client.get(reverse("admin:members_membertag_delete", args=[tag.pk]))

    assert response.status_code == 403
    assert MemberTag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db
def test_tag_admin_does_not_offer_bulk_delete(superuser):
    request = RequestFactory().get("/admin/members/membertag/")
    request.user = superuser
    tag_admin = admin.site._registry[MemberTag]

    assert "delete_selected" not in tag_admin.get_actions(request)


@pytest.mark.django_db
def test_tag_can_be_deleted_after_mailing_list_criterion_is_removed(client, superuser):
    tag = MemberTag.objects.create(key="removable", display_label="Removable")
    mailing_list = MailingList.objects.create(
        name="removable-tag-list", criteria=[f"tag:{tag.key}"]
    )
    client.force_login(superuser)

    blocked = client.get(reverse("admin:members_membertag_delete", args=[tag.pk]))
    assert blocked.status_code == 403

    mailing_list.criteria = []
    mailing_list.save(update_fields=["criteria"])
    response = client.post(
        reverse("admin:members_membertag_delete", args=[tag.pk]), {"post": "yes"}
    )

    assert response.status_code == 302
    assert not MemberTag.objects.filter(pk=tag.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_direct_and_queryset_tag_deletion_are_blocked_by_safety_guard():
    tag = MemberTag.objects.create(key="guarded", display_label="Guarded")
    MailingList.objects.create(name="guarded-tag-list", criteria=[f"tag:{tag.key}"])

    with pytest.raises(ValidationError, match="Cannot delete tag"):
        tag.delete()
    with pytest.raises(ValidationError, match="Cannot delete tag"):
        MemberTag.objects.filter(pk=tag.pk).delete()

    assert MemberTag.objects.filter(pk=tag.pk).exists()

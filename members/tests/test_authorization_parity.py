import json

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.core.management.base import CommandError

from members.models import Member
from members.parity import (
    build_authorization_snapshot,
    compare_authorization_snapshot_details,
    compare_authorization_snapshots,
)
from siteconfig.models import MailingList, MembershipStatus


@pytest.mark.django_db
def test_snapshot_hashes_recipients_and_captures_legacy_permissions():
    MembershipStatus.objects.update_or_create(
        name="Full Member", defaults={"is_active": True}
    )
    member = Member.objects.create_user(
        username="parity-member",
        email="Parity@example.com",
        membership_status="Full Member",
    )
    group = Group.objects.create(name="Parity Role")
    group.permissions.add(
        Permission.objects.get(content_type__app_label="auth", codename="view_group")
    )
    member.groups.add(group)
    MailingList.objects.create(name="parity-list", criteria=["active_member"])

    snapshot = build_authorization_snapshot(legacy_compatible=True)

    assert snapshot["projection"] == "legacy"
    assert "branch" not in snapshot
    assert "recipients" not in snapshot["legacy"]["recipients"]["parity-list"]
    assert snapshot["legacy"]["recipients"]["parity-list"]["recipient_count"] == 1
    member_snapshot = snapshot["legacy"]["authorization"]["members"][member.username]
    assert member_snapshot["groups"][0]["name"] == "Parity Role"
    assert "auth.view_group" in member_snapshot["effective_permissions"]
    assert snapshot["schema"]["migration_heads"]


@pytest.mark.django_db
def test_legacy_projection_does_not_query_branch_models(monkeypatch):
    monkeypatch.setattr(
        "members.parity._branch_projection",
        lambda **kwargs: pytest.fail("legacy projection queried branch models"),
    )

    snapshot = build_authorization_snapshot(projection="legacy")

    assert snapshot["projection"] == "legacy"
    assert "branch" not in snapshot


def test_incompatible_snapshot_versions_are_rejected():
    before = {"snapshot_version": 1}
    after = {"snapshot_version": 1}

    with pytest.raises(ValueError, match="unsupported snapshot version"):
        compare_authorization_snapshots(before, after)


def test_branch_additions_are_not_reported_as_legacy_parity_changes():
    legacy = {
        "authorization": {"members": {}},
        "recipients": {},
    }
    before = {
        "snapshot_version": 2,
        "projection": "legacy",
        "schema": {"migration_heads": {"members": ["0033"]}},
        "legacy": legacy,
    }
    after = {
        **before,
        "projection": "full",
        "schema": {"migration_heads": {"members": ["0052"]}},
        "branch": {
            "roles": [{"key": "new-role", "group_name": "New Role"}],
            "assignments": [],
        },
    }

    assert compare_authorization_snapshots(before, after) == []
    details = compare_authorization_snapshot_details(before, after)
    assert details["branch_comparable"] is False
    assert details["branch_differences"] == []
    assert details["schema_changed"] is True


@pytest.mark.django_db
def test_snapshot_commands_keep_hashes_and_refuse_overwrite(tmp_path):
    before = tmp_path / "before.json"
    call_command("capture_authorization_parity", "--legacy-compatible", str(before))
    snapshot = json.loads(before.read_text())

    assert snapshot["projection"] == "legacy"
    assert all(
        "recipients" not in data for data in snapshot["legacy"]["recipients"].values()
    )
    with pytest.raises(CommandError, match="Refusing to overwrite"):
        call_command("capture_authorization_parity", "--legacy-compatible", str(before))

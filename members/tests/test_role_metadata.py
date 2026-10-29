from importlib import import_module
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from members.models import RoleMetadata
from siteconfig.models import MailingListCriterion

role_metadata_migration = import_module("members.migrations.0034_role_metadata")

CANONICAL_ROLES = {
    "Instructor Admins": "instructor_admins",
    "Webmasters": "webmasters",
    "Member Managers": "member_managers",
    "Rostermeisters": "rostermeisters",
    "Secretary": "secretary",
    "Treasurer": "treasurer",
}

CANONICAL_MAILING_LIST_CRITERIA = {
    "Instructor Admins": MailingListCriterion.INSTRUCTOR,
    "Webmasters": MailingListCriterion.WEBMASTER,
    "Member Managers": MailingListCriterion.MEMBER_MANAGER,
    "Rostermeisters": MailingListCriterion.ROSTERMEISTER,
    "Secretary": MailingListCriterion.SECRETARY,
    "Treasurer": MailingListCriterion.TREASURER,
}


class _FakeQuerySet(list):
    def using(self, _alias):
        return self

    def filter(self, **filters):
        return _FakeQuerySet(
            item
            for item in self
            if all(getattr(item, field) == value for field, value in filters.items())
        )

    def order_by(self, _field):
        return _FakeQuerySet(sorted(self, key=lambda item: item.pk))

    def first(self):
        return self[0] if self else None


class _FakeManager(_FakeQuerySet):
    pass


def _fake_migration_apps(groups, metadata=()):
    group_model = SimpleNamespace(objects=_FakeManager(groups))
    metadata_model = SimpleNamespace(objects=_FakeManager(metadata))

    def get_model(app_label, model_name):
        if (app_label, model_name) == ("auth", "Group"):
            return group_model
        if (app_label, model_name) == ("members", "RoleMetadata"):
            return metadata_model
        raise AssertionError((app_label, model_name))

    return SimpleNamespace(get_model=get_model)


def _fake_schema_editor():
    return SimpleNamespace(connection=SimpleNamespace(alias="default"))


def _fake_canonical_groups():
    return [
        SimpleNamespace(pk=index, name=name)
        for index, name in enumerate(CANONICAL_ROLES, start=1)
    ]


def test_metadata_seed_fails_for_missing_canonical_group():
    groups = _fake_canonical_groups()[:-1]

    with pytest.raises(RuntimeError, match="Treasurer.*missing"):
        role_metadata_migration.seed_canonical_role_metadata(
            _fake_migration_apps(groups), _fake_schema_editor()
        )


def test_metadata_seed_fails_for_duplicate_canonical_group():
    groups = _fake_canonical_groups()
    groups.append(SimpleNamespace(pk=99, name="Treasurer"))

    with pytest.raises(RuntimeError, match="Treasurer.*duplicate"):
        role_metadata_migration.seed_canonical_role_metadata(
            _fake_migration_apps(groups), _fake_schema_editor()
        )


def test_metadata_seed_fails_for_stable_key_collision():
    collision = SimpleNamespace(pk=101, group_id=999, key="instructor_admins")

    with pytest.raises(RuntimeError, match="instructor_admins.*already used"):
        role_metadata_migration.seed_canonical_role_metadata(
            _fake_migration_apps(_fake_canonical_groups(), [collision]),
            _fake_schema_editor(),
        )


@pytest.mark.django_db
def test_canonical_groups_have_stable_role_metadata():
    metadata = RoleMetadata.objects.select_related("group").order_by("sort_order")

    assert metadata.count() == len(CANONICAL_ROLES)
    assert [(item.group.name, item.key) for item in metadata] == list(
        CANONICAL_ROLES.items()
    )
    assert all(item.display_name == item.group.name for item in metadata)
    assert all(item.is_builtin for item in metadata)
    assert all(item.is_protected for item in metadata)
    assert all(item.is_system_managed for item in metadata)
    assert all(item.is_assignable for item in metadata)
    assert all(item.mailing_list_eligible for item in metadata)
    assert set(CANONICAL_MAILING_LIST_CRITERIA.values()) == {
        criterion.value for criterion in MailingListCriterion
    } - {
        MailingListCriterion.ACTIVE_MEMBER,
        MailingListCriterion.TOWPILOT,
        MailingListCriterion.DUTY_OFFICER,
        MailingListCriterion.ASSISTANT_DUTY_OFFICER,
        MailingListCriterion.DIRECTOR,
        MailingListCriterion.SAFETY_OFFICER,
        MailingListCriterion.PRIVATE_GLIDER_OWNER,
    }


@pytest.mark.django_db
def test_role_metadata_is_one_to_one_and_key_is_unique():
    group = Group.objects.create(name="Custom role")
    metadata = RoleMetadata.objects.create(
        group=group,
        key="custom_role",
        display_name="Custom role",
    )

    assert group.role_metadata == metadata
    with pytest.raises(ValidationError):
        RoleMetadata.objects.create(
            group=group,
            key="another_custom_role",
            display_name="Another custom role",
        )
    with pytest.raises(ValidationError):
        RoleMetadata.objects.create(
            group=Group.objects.create(name="Another role"),
            key="custom_role",
            display_name="Another custom role",
        )
    group.delete()
    assert not RoleMetadata.objects.filter(pk=metadata.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_metadata_migration_preserves_groups_memberships_and_permissions():
    """0034 only adds metadata; it must not rewrite existing Group state."""
    executor = MigrationExecutor(connection)
    original_leaf_targets = executor.loader.graph.leaf_nodes()
    before = ("members", "0033_member_manager_emergency_contact_permissions")
    after = ("members", "0034_role_metadata")

    executor.migrate([before])
    old_apps = executor.loader.project_state([before]).apps
    OldGroup = old_apps.get_model("auth", "Group")
    OldMember = old_apps.get_model("members", "Member")
    OldPermission = old_apps.get_model("auth", "Permission")

    legacy_group = OldGroup.objects.create(name="Legacy custom group")
    equipment_group = OldGroup.objects.create(name="Club Equipment Coordinators")
    member = OldMember.objects.create(username="legacy-group-member")
    second_member = OldMember.objects.create(username="legacy-equipment-member")
    permission_rows = list(OldPermission.objects.order_by("pk")[:2])
    assert len(permission_rows) == 2
    legacy_group.user_set.add(member, second_member)
    equipment_group.user_set.add(second_member)
    legacy_group.permissions.add(permission_rows[0])
    equipment_group.permissions.add(permission_rows[1])

    def snapshot():
        return {
            group.name: {
                "members": set(group.user_set.values_list("pk", flat=True)),
                "permissions": set(group.permissions.values_list("pk", flat=True)),
            }
            for group in OldGroup.objects.order_by("pk")
        }

    group_snapshot = snapshot()

    try:
        # MigrationExecutor caches applied migrations; refresh it after moving
        # to the historical state before calculating the forward plan.
        executor = MigrationExecutor(connection)
        executor.migrate([after])
        new_apps = MigrationExecutor(connection).loader.project_state([after]).apps
        NewRoleMetadata = new_apps.get_model("members", "RoleMetadata")

        assert snapshot() == group_snapshot
        assert set(NewRoleMetadata.objects.values_list("key", flat=True)) == set(
            CANONICAL_ROLES.values()
        )
        assert set(
            NewRoleMetadata.objects.values_list("group__name", flat=True)
        ) == set(CANONICAL_ROLES)
        assert not NewRoleMetadata.objects.filter(
            group__name__in=(legacy_group.name, equipment_group.name)
        ).exists()
    finally:
        MigrationExecutor(connection).migrate(original_leaf_targets)

import pytest

from members.models import RoleMetadata
from members.role_definitions import (
    CANONICAL_ROLES,
    CAPABILITY_GRANTS,
    ROLE_BY_GROUP_NAME,
    ROLE_BY_KEY,
    legacy_sync_group_names,
)


def test_canonical_roles_have_unique_stable_identity():
    assert len(ROLE_BY_KEY) == len(CANONICAL_ROLES)
    assert len(ROLE_BY_GROUP_NAME) == len(CANONICAL_ROLES)
    assert [role.sort_order for role in CANONICAL_ROLES]
    assert all(role.key and role.group_name for role in CANONICAL_ROLES)


def test_capability_grants_use_stable_role_keys():
    assert set(CAPABILITY_GRANTS) <= set(ROLE_BY_KEY)
    assert all(
        capability.count(".") == 1
        for capabilities in CAPABILITY_GRANTS.values()
        for capability in capabilities
    )


def test_legacy_sync_registry_preserves_existing_flag_driven_groups():
    assert legacy_sync_group_names() == {
        "Instructor Admins": "instructor",
        "Webmasters": "webmaster",
        "Member Managers": "member_manager",
        "Rostermeisters": "rostermeister",
        "Secretary": "secretary",
        "Treasurer": "treasurer",
        "Directors": "director",
    }


@pytest.mark.django_db
def test_database_builtin_roles_have_registered_capabilities():
    for role_key, capabilities in CAPABILITY_GRANTS.items():
        metadata = RoleMetadata.objects.select_related("group").get(key=role_key)
        actual = {
            f"{permission.content_type.app_label}.{permission.codename}"
            for permission in metadata.group.permissions.select_related("content_type")
        }
        assert set(capabilities) <= actual, role_key

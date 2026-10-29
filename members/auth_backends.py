"""Authentication backend for current qualification permission bundles."""

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils import timezone


class QualificationPermissionBackend(BaseBackend):
    """Grant bundle permissions without changing ordinary Group membership.

    This intentionally implements only global permissions.  Object permissions
    remain the responsibility of the application's object-level policies.
    The query is performed for every check; qualification grants must not be
    retained in Django's per-user permission cache across expiry or revocation.
    """

    def get_group_permissions(self, user_obj, obj=None):
        if obj is not None or not user_obj.is_active or not user_obj.is_active_member():
            return set()

        today = timezone.localdate()
        from instructors.models import (
            QUALIFICATION_ADMIN_PERMISSION_CODENAMES,
            QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES,
            MemberQualification,
            QualificationPermissionGrant,
        )

        permission_groups = (
            MemberQualification.objects.filter(
                member=user_obj,
                is_qualified=True,
                qualification__is_obsolete=False,
            )
            .filter(Q(expiration_date__gte=today) | Q(expiration_date__isnull=True))
            .values_list("qualification__permission_group_id", flat=True)
        )
        # The permission_group relation is optional; exclude NULL IDs and keep
        # the bundle opt-in as a defense against stale/inconsistent rows.
        approved_permissions = QualificationPermissionGrant.objects.filter(
            group_id__in=permission_groups
        ).values_list("permission_id", flat=True)
        permissions = (
            Permission.objects.filter(
                id__in=approved_permissions,
                group__id__in=permission_groups,
                group__role_metadata__qualification_permission_bundle=True,
                group__role_metadata__is_builtin=False,
                group__role_metadata__is_protected=False,
                group__role_metadata__is_system_managed=False,
            )
            .exclude(
                Q(
                    content_type__app_label__in=(
                        "admin",
                        "auth",
                        "contenttypes",
                        "sessions",
                    )
                )
                | Q(
                    content_type__app_label="members",
                    content_type__model__in=(
                        "member",
                        "rolemetadata",
                        "memberroleassignment",
                    ),
                )
                | Q(
                    content_type__app_label="instructors",
                    codename__in=QUALIFICATION_ADMIN_PERMISSION_CODENAMES,
                )
                | Q(
                    codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                        0
                    ]
                )
                | Q(
                    codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                        1
                    ]
                )
                | Q(
                    codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                        2
                    ]
                )
                | Q(
                    codename__startswith=QUALIFICATION_STANDARD_PERMISSION_CODENAME_PREFIXES[
                        3
                    ]
                )
            )
            .values_list("content_type__app_label", "codename")
        )
        return {f"{app_label}.{codename}" for app_label, codename in permissions}

    def get_all_permissions(self, user_obj, obj=None):
        if obj is not None:
            return set()
        return self.get_group_permissions(user_obj, obj=obj)

"""Authentication backend for current qualification permission bundles."""

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import Permission
from django.db.models import F, Q
from django.utils import timezone


class QualificationPermissionBackend(BaseBackend):
    """Grant bundle permissions without changing ordinary Group membership.

    This intentionally implements only global permissions.  Object permissions
    remain the responsibility of the application's object-level policies.
    The query is performed for every check; qualification grants must not be
    retained in Django's per-user permission cache across expiry or revocation.
    """

    def has_perm(self, user_obj, perm, obj=None):
        from instructors.models import QUALIFICATION_ALLOWED_PERMISSIONS

        if perm not in QUALIFICATION_ALLOWED_PERMISSIONS:
            return False
        return perm in self.get_all_permissions(user_obj, obj=obj)

    def get_group_permissions(self, user_obj, obj=None):
        if obj is not None or not user_obj.is_active or not user_obj.is_active_member():
            return set()

        from instructors.models import (
            QUALIFICATION_ALLOWED_PERMISSIONS,
            MemberQualification,
            QualificationPermissionGrant,
        )

        today = timezone.localdate()

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
        allowed_filters = Q()
        for capability in QUALIFICATION_ALLOWED_PERMISSIONS:
            app_label, codename = capability.split(".", 1)
            allowed_filters |= Q(
                content_type__app_label=app_label,
                codename=codename,
            )
        permissions = (
            QualificationPermissionGrant.objects.filter(
                group_id__in=permission_groups,
                permission__group__id=F("group_id"),
                group__role_metadata__qualification_permission_bundle=True,
                group__role_metadata__is_builtin=False,
                group__role_metadata__is_protected=False,
                group__role_metadata__is_system_managed=False,
            )
            .filter(permission__in=Permission.objects.filter(allowed_filters))
            .values_list("permission__content_type__app_label", "permission__codename")
        )
        return {f"{app_label}.{codename}" for app_label, codename in permissions}

    def get_all_permissions(self, user_obj, obj=None):
        if obj is not None:
            return set()
        return self.get_group_permissions(user_obj, obj=obj)

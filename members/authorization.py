"""Small, read-only authorization decision boundary for application policies.

Callers own contextual policies (ownership, assignments, etc.) and pass their
result explicitly. This module does not interpret legacy flags, inspect objects,
validate kiosk sessions, audit access, or implement role preview. A future preview
must supply a separate effective principal/policy at this boundary rather than
silently borrowing the administrator's real permissions.
"""

from dataclasses import dataclass

from members.utils.membership import is_active_member


def has_webmaster_compatibility_access(user):
    """Return the legacy webmaster-level grant used during the transition.

    The flag and group are intentionally retained as compatibility fallbacks;
    neither ordinary staff status nor membership status grants this access.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "webmaster", False)
        or user.groups.filter(name="Webmasters").exists()
    )


def has_admin_model_permission(user, app_label, model_name, action):
    """Check one admin model permission with legacy webmaster fallbacks."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        user.has_perm(f"{app_label}.{action}_{model_name}")
        or has_webmaster_compatibility_access(user)
    )


def has_role_admin_access(user):
    """Return whether an active account has a role-level admin entry grant.

    This is an additive transition boundary.  Django's default admin site
    still uses ``is_staff`` until its entry gate is migrated, but application
    authorization must not use ``is_staff`` as a business permission.  The
    role flag only controls entry visibility; model/action permissions remain
    separate.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return user.groups.filter(role_metadata__admin_access=True).exists()


@dataclass(frozen=True)
class AuthorizationDecision:
    """An allow/deny result with a stable, machine-readable reason."""

    allow: bool
    reason: str


def resolve_authorization(
    user,
    permission: str,
    *,
    context_allow: bool = False,
    require_active_member: bool = False,
    kiosk_authenticated: bool = False,
    allow_kiosk_membership_bypass: bool = False,
) -> AuthorizationDecision:
    """Decide access from global permission OR an explicit contextual grant.

    ``permission`` is a Django ``app_label.codename`` global permission;
    ``user.has_perm(permission)`` is the sole global-permission authority.
    ``context_allow`` must be computed by the caller for this exact action and
    context, not inferred from identity or legacy flags. Anonymous and inactive
    accounts are denied before either grant. Set ``require_active_member`` for
    member-only actions; superusers follow ``is_active_member``'s default policy.

    A trusted caller may pass ``kiosk_authenticated=True`` AND opt in to
    ``allow_kiosk_membership_bypass`` for a kiosk-eligible action. This skips only
    the optional membership-status gate, never the account gate or capability
    check. Neither a kiosk token nor a session flag is verified here. Defaults
    never grant a kiosk bypass. No database writes, audit events, or caching.

    Django's ModelBackend caches ordinary user/group permissions on each user
    object. Callers changing those grants must use a fresh user instance (or
    clear Django's permission caches); this resolver does not mutate that cache.
    The qualification backend queries current grants on each ``has_perm`` call,
    so qualification expiry/revocation remains fresh even on the same user.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return AuthorizationDecision(False, "unauthenticated")
    if not getattr(user, "is_active", False):
        return AuthorizationDecision(False, "inactive_account")
    if require_active_member and not (
        kiosk_authenticated and allow_kiosk_membership_bypass
    ):
        if not is_active_member(user):
            return AuthorizationDecision(False, "inactive_membership")
    if user.has_perm(permission):
        return AuthorizationDecision(True, "global_permission")
    if context_allow:
        return AuthorizationDecision(True, "context_grant")
    return AuthorizationDecision(False, "no_grant")

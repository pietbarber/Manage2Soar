"""Session-based role preview for administrators and local developers."""

import logging
from dataclasses import dataclass
from functools import wraps
from types import MethodType

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from members.models import RoleMetadata
from members.role_definitions import ROLE_BY_KEY
from members.utils.membership import is_active_member

SESSION_KEY = "role_preview"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CONTROL_PATHS = {
    "/members/role-preview/",
    "/members/role-preview/start/",
    "/members/role-preview/stop/",
}
ROLE_FLAG_KEYS = (
    "director",
    "instructor",
    "member_manager",
    "rostermeister",
    "safety_officer",
    "secretary",
    "stats_monger",
    "treasurer",
    "webmaster",
)
logger = logging.getLogger(__name__)


def _log_preview_event(request, outcome, *, role=None, debug=None, reason=None):
    """Log a preview decision with fields usable by structured log handlers."""
    user = getattr(request, "user", None)
    actor = user.get_username() if user is not None else None
    event = {
        "outcome": outcome,
        "actor": actor,
        "role": role,
        "debug": debug,
        "reason": reason,
        "method": request.method,
        "path": request.path,
    }
    logger.info(
        "Role preview event: outcome=%s actor=%s role=%s debug=%s reason=%s "
        "method=%s path=%s",
        outcome,
        actor,
        role,
        debug,
        reason,
        request.method,
        request.path,
        extra={
            **event,
            "role_preview_event": event,
            "role_preview_outcome": outcome,
        },
    )


@dataclass(frozen=True)
class PreviewState:
    role_key: str
    display_name: str
    group_name: str
    permissions: frozenset[str]
    debug: bool = False

    def as_context(self):
        return {
            "active": True,
            "role_key": self.role_key,
            "display_name": self.display_name,
            "group_name": self.group_name,
            "debug": self.debug,
        }


def can_manage_preview(user):
    """Allow only active superusers to manage role previews.

    ``RoleMetadata.admin_access`` is an administrative-site entry grant, not a
    role-preview capability.  Until a separate, deliberately scoped platform
    administrator policy exists, ordinary role holders must not be able to
    select an arbitrary role and project its permissions onto their account.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(
        getattr(user, "is_active", False) and getattr(user, "is_superuser", False)
    )


def _load_state(request):
    raw = request.session.get(SESSION_KEY)
    if not raw or not isinstance(raw, dict):
        return None
    role_key = raw.get("role_key")
    metadata = RoleMetadata.objects.select_related("group").filter(key=role_key).first()
    if metadata is None:
        return None
    permissions = frozenset(
        f"{permission.content_type.app_label}.{permission.codename}"
        for permission in metadata.group.permissions.select_related("content_type")
    )
    return PreviewState(
        role_key=metadata.key,
        display_name=metadata.display_name,
        group_name=metadata.group.name,
        permissions=permissions,
        # A session value must never enable debug behavior after DEBUG is
        # turned off or after a session is copied between environments.
        debug=bool(raw.get("debug", False) and settings.DEBUG),
    )


def get_preview_state(request):
    # Middleware attaches the already-authorized state before projecting the
    # user.  Do not re-check the projected user here: it intentionally no
    # longer has superuser status.  Conversely, do not load a session state for
    # an ordinary user who may have inherited or tampered with a stale session.
    state = getattr(request, "role_preview", None)
    if state is not None:
        return state
    if not can_manage_preview(getattr(request, "user", None)):
        return None
    return _load_state(request)


def has_preview_group(user, group_name):
    """Check a group while honoring the selected role during preview."""
    preview_group = getattr(user, "_role_preview_group_name", None)
    if preview_group is not None:
        return preview_group == group_name
    return user.groups.filter(name=group_name).exists()


def _role_metadata():
    return RoleMetadata.objects.select_related("group").order_by(
        "sort_order", "display_name", "pk"
    )


def _preview_manager_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            _log_preview_event(request, "rejected", reason="unauthenticated")
            return redirect_to_login(request.get_full_path())
        if not can_manage_preview(request.user):
            _log_preview_event(request, "rejected", reason="not_authorized")
            return HttpResponseForbidden(
                "Role preview is restricted to administrators."
            )
        return view(request, *args, **kwargs)

    return wrapped


@require_GET
@_preview_manager_required
def role_preview(request):
    return render(
        request,
        "members/role_preview.html",
        {
            "roles": _role_metadata(),
            "role_preview": get_preview_state(request),
            "debug_available": settings.DEBUG,
        },
    )


@require_POST
@_preview_manager_required
def start_role_preview(request):
    role_key = request.POST.get("role_key", "")
    metadata = _role_metadata().filter(key=role_key).first()
    if metadata is None:
        _log_preview_event(
            request, "rejected", role=role_key or None, reason="unknown_role"
        )
        return HttpResponseForbidden("Unknown preview role.")
    debug = request.POST.get("debug") == "on"
    if debug and not settings.DEBUG:
        _log_preview_event(
            request,
            "rejected",
            role=metadata.key,
            debug=debug,
            reason="debug_disabled",
        )
        return HttpResponseForbidden("Debug role preview is disabled.")
    request.session[SESSION_KEY] = {"role_key": metadata.key, "debug": debug}
    request.session.modified = True
    _log_preview_event(request, "start", role=metadata.key, debug=debug)
    return redirect("members:role_preview")


@require_POST
@_preview_manager_required
def stop_role_preview(request):
    previous = request.session.get(SESSION_KEY)
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
    _log_preview_event(
        request,
        "stop",
        role=previous.get("role_key") if isinstance(previous, dict) else None,
    )
    return redirect("members:role_preview")


def role_preview_context(request):
    state = get_preview_state(request)
    return {"role_preview": state.as_context() if state else None}


class RolePreviewMiddleware:
    """Project a selected role onto the request without changing the user row."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        state = _load_state(request) if request.user.is_authenticated else None
        if state is None or not can_manage_preview(request.user):
            return self.get_response(request)

        request.role_preview = state
        # Preview controls must continue to run as the real administrator;
        # otherwise the projected role would fail its own start/stop gate.
        if request.path in CONTROL_PATHS:
            return self.get_response(request)
        if (
            request.method not in SAFE_METHODS
            and not state.debug
            and request.path not in CONTROL_PATHS
        ):
            _log_preview_event(
                request,
                "blocked",
                role=state.role_key,
                debug=state.debug,
                reason="read_only",
            )
            return HttpResponseForbidden(
                "Role preview is read-only. Enable DEBUG preview to test edits."
            )

        user = request.user
        original = {}
        for name in ("has_perm", "has_module_perms", "get_all_permissions"):
            original[name] = getattr(user, name)
        for name in (*ROLE_FLAG_KEYS, "is_superuser", "is_staff"):
            original[name] = getattr(user, name)
        original["_role_preview_group_name"] = getattr(
            user, "_role_preview_group_name", None
        )
        original["_role_preview_active_member"] = getattr(
            user, "_role_preview_active_member", None
        )
        user._role_preview_active_member = is_active_member(user)

        def has_perm(_user, permission, obj=None):
            return permission in state.permissions

        def has_module_perms(_user, app_label):
            return any(
                permission.startswith(f"{app_label}.")
                for permission in state.permissions
            )

        def get_all_permissions(_user):
            return state.permissions

        user.has_perm = MethodType(has_perm, user)
        user.has_module_perms = MethodType(has_module_perms, user)
        user.get_all_permissions = MethodType(get_all_permissions, user)
        for name in ROLE_FLAG_KEYS:
            role = ROLE_BY_KEY.get(state.role_key)
            setattr(user, name, bool(role and role.legacy_flag == name))
        user.is_superuser = False
        user.is_staff = False
        user._role_preview_group_name = state.group_name
        try:
            return self.get_response(request)
        finally:
            for name, value in original.items():
                if name == "_role_preview_active_member" and value is None:
                    delattr(user, name)
                else:
                    setattr(user, name, value)
            if original["_role_preview_group_name"] is None:
                delattr(user, "_role_preview_group_name")
            else:
                user._role_preview_group_name = original["_role_preview_group_name"]

"""Request-scoped attribution for role-assignment audit events.

The deletion signal records revocations for every assignment deletion,
including cascades from Group/Member deletion.  Callers that know the acting
user wrap the deletion in :func:`actor_scope` so the event can retain
attribution without teaching the signal about HTTP requests.
"""

from contextlib import contextmanager
from contextvars import ContextVar

_actor = ContextVar("role_assignment_audit_actor", default=None)
_internal_group_write = ContextVar(
    "role_assignment_audit_internal_group_write", default=False
)


def get_actor():
    return _actor.get()


def is_internal_group_write():
    return _internal_group_write.get()


@contextmanager
def actor_scope(actor):
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)


@contextmanager
def internal_group_write_scope():
    """Mark M2M writes made by supported role-management paths."""
    token = _internal_group_write.set(True)
    try:
        yield
    finally:
        _internal_group_write.reset(token)

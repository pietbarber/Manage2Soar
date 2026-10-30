"""Request-scoped attribution for role-assignment audit events.

The deletion signal records revocations for every assignment deletion,
including cascades from Group/Member deletion.  Callers that know the acting
user wrap the deletion in :func:`actor_scope` so the event can retain
attribution without teaching the signal about HTTP requests.
"""

from contextlib import contextmanager
from contextvars import ContextVar

_actor = ContextVar("role_assignment_audit_actor", default=None)


def get_actor():
    return _actor.get()


@contextmanager
def actor_scope(actor):
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)

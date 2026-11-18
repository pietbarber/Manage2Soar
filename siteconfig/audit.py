"""Attribution context for membership-status mapping audit events."""

from contextlib import contextmanager
from contextvars import ContextVar

_actor = ContextVar("membership_status_mapping_actor", default=None)


def get_actor():
    return _actor.get()


@contextmanager
def actor_scope(actor):
    token = _actor.set(actor)
    try:
        yield
    finally:
        _actor.reset(token)

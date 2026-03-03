# logsheet/templatetags/logsheet_tags.py
from datetime import timedelta

from django import template

register = template.Library()


@register.filter
def can_be_resolved_by(issue, user):
    return issue.can_be_resolved_by(user)


@register.filter
def format_duration(value):
    """Format a timedelta (or None) as H:MM for display in flight logs.

    Examples:  timedelta(minutes=23) → '0:23'
               timedelta(hours=1, minutes=5) → '1:05'
               None → ''
    """
    if value is None:
        return ""
    if not isinstance(value, timedelta):
        return str(value)
    total_seconds = int(value.total_seconds())
    if total_seconds < 0:
        return ""
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{hours}:{minutes:02d}"


@register.filter
def bs_tag(tag):
    """Normalise a Django message tag to a valid Bootstrap colour variant.

    Django's MESSAGE_TAGS already maps ``error → danger``, but ``debug``
    has no Bootstrap equivalent and would produce an invalid ``text-bg-debug``
    class.  Map it to ``secondary`` so toasts stay readable.
    """
    return "secondary" if tag == "debug" else tag

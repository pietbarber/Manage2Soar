from django import template

from duty_roster.models import DutyRosterMessage
from members.utils.permissions import contact_field_visibility

register = template.Library()


@register.filter
def dict_get(d, key):
    return d.get(key)


@register.simple_tag
def contact_field_is_shared(member, field, site_config=None):
    return contact_field_visibility(member, field, site_config)["shared"]


@register.simple_tag
def get_roster_message():
    """
    Get the current active roster message (Issue #551).

    Returns:
        DutyRosterMessage instance or None if no active message exists.

    Usage in templates:
        {% load duty_extras %}
        {% get_roster_message as roster_message %}
        {% if roster_message %}
            {{ roster_message.content|safe }}
        {% endif %}
    """
    return DutyRosterMessage.get_message()

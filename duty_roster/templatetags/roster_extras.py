import json

from django import template
from django.core.serializers.json import DjangoJSONEncoder

from members.models import Member

register = template.Library()


@register.filter
def get_member_name(member_id):
    try:
        return Member.objects.get(pk=member_id).full_display_name
    except Member.DoesNotExist:
        return "❓"


# duty_roster/templatetags/roster_extras.py
@register.filter
def dict_get(d, key):
    return d.get(key)


@register.filter
def to_json(value):
    """Convert a Python object to JSON string.

    Uses Django's JSON encoder to handle dates, decimals, etc.
    When embedding in HTML attributes, callers should use |escape filter
    to prevent XSS (e.g., {{ value|to_json|escape }}).
    """
    return json.dumps(value, cls=DjangoJSONEncoder)

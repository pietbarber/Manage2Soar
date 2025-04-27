from django import template
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

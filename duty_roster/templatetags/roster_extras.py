from django import template
from members.models import Member

register = template.Library()

@register.filter
def get_member_name(member_id):
    try:
        return Member.objects.get(pk=member_id).full_display_name
    except Member.DoesNotExist:
        return "❓"

# logsheet/templatetags/logsheet_tags.py
from django import template

register = template.Library()

@register.filter
def can_be_resolved_by(issue, user):
    return issue.can_be_resolved_by(user)

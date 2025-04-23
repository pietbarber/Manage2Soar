# duty_roster/templatetags/calendar_tags.py

from django import template
from calendar import Calendar
from datetime import timedelta

register = template.Library()

@register.filter
def make_week_chunks(days):
    calendar = Calendar()
    weeks = []
    week = []
    for day in days:
        week.append(day)
        if len(week) == 7:
            weeks.append(week)
            week = []
    if week:
        while len(week) < 7:
            week.append(None)
        weeks.append(week)
    return weeks

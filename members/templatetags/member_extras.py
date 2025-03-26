# ya know, sometimes, I don't want to construct a person's name from all these fields.
# This is a small template filter that will display a member's name in a more human-readable format.
# I wish people would be simple with a first name and a last name. Why do they have to be all difficult
# with name suffixes, and middle initials, and nicknames? 😂


from django import template
import re

register = template.Library()

@register.filter
def full_display_name(member):
    """Returns the member's full display name with nickname, middle initial, suffix, etc."""
    if not member:
        return ""

    parts = []
    if member.first_name:
        parts.append(member.first_name)

    if member.middle_initial:
        parts.append(member.middle_initial)

    if member.nickname:
        parts.append(f'“{member.nickname}”')

    if member.last_name:
        parts.append(member.last_name)

    if member.name_suffix:
        parts.append(member.name_suffix)

    return " ".join(parts)

@register.filter
def format_us_phone(value):
    """Format a 10-digit US phone number into +1-AAA-BBB-CCCC"""
    digits = re.sub(r'\D', '', str(value))
    if len(digits) == 10:
        return f"+1 {digits[0:3]}-{digits[3:6]}-{digits[6:]}"
    return value  # Fallback: return original

@register.filter
def render_duties(member):
    duties = []
    if member.instructor:
        duties.append('<span title="Instructor">🧑‍🏫</span>')
    if member.towpilot:
        duties.append('<span title="Tow Pilot">✈️</span>')
    if member.duty_officer:
        duties.append('<span title="Duty Officer">📋</span>')
    if member.assistant_duty_officer:
        duties.append('<span title="Assistant DO">🧑‍💼</span>')
    if member.secretary:
        duties.append('<span title="Secretary">📝</span>')
    if member.treasurer:
        duties.append('<span title="Treasurer">💰</span>')
    if member.webmaster:
        duties.append('<span title="Webmaster">🌐</span>')
    if member.director:
        duties.append('<span title="Director">🎖️</span>')
    if member.member_manager:
        duties.append('<span title="Membership Manager">🧑‍🔧</span>')

    return ' '.join(duties) if duties else "-"

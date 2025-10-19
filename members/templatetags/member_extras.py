# ya know, sometimes, I don't want to construct a person's name
# from all these fields.
# This is a small template filter.
# It will display a member's name in a more human-readable format.
# I wish people would be simple with a first name and a last name.
# Why do they have to be all difficult with name suffixes,
# middle initials, and nicknames? 😂


import re

from django import template
from django.utils.safestring import mark_safe

from siteconfig.models import SiteConfiguration

register = template.Library()


@register.filter
def full_display_name(member):
    """
    Returns the member's full display name with nickname, middle initial,
    suffix, etc.
    """
    if not member:
        return ""

    parts = []
    if member.first_name:
        parts.append(member.first_name)

    if member.middle_initial:
        parts.append(member.middle_initial)

    if member.nickname:
        parts.append(f"“{member.nickname}”")

    if member.last_name:
        parts.append(member.last_name)

    if member.name_suffix:
        parts.append(member.name_suffix)

    return " ".join(parts)


@register.filter
def format_us_phone(value):
    """Format a 10-digit US phone number into +1-AAA-BBB-CCCC"""
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 10:
        return f"+1 {digits[0:3]}-{digits[3:6]}-{digits[6:]}"
    return value  # Fallback: return original


@register.simple_tag
def duty_emoji_legend():
    """Return the emoji legend HTML used by members templates."""
    config = SiteConfiguration.objects.first()
    instructor = (
        getattr(config, "instructor_title", "Instructor") if config else "Instructor"
    )
    towpilot = getattr(config, "towpilot_title", "Tow Pilot") if config else "Tow Pilot"
    duty_officer = (
        getattr(config, "duty_officer_title", "Duty Officer")
        if config
        else "Duty Officer"
    )
    assistant_duty_officer = (
        getattr(config, "assistant_duty_officer_title", "Assistant Duty Officer")
        if config
        else "Assistant Duty Officer"
    )

    parts = [
        "<div class='accordion mb-4' id='emojiLegendAccordion'>",
        "<div class='accordion-item'>",
        "<h2 class='accordion-header' id='headingLegend'>",
        "<button class='accordion-button collapsed' ",
        "type='button' data-bs-toggle='collapse' ",
        "data-bs-target='#collapseLegend' aria-expanded='false' ",
        "aria-controls='collapseLegend'>",
        "📖 Expand to show Legend</button>",
        "</h2>",
        "<div id='collapseLegend' class='accordion-collapse collapse' ",
        "aria-labelledby='headingLegend' ",
        "data-bs-parent='#emojiLegendAccordion'>",
        "<div class='accordion-body'>",
        "<ul class='list-unstyled mb-0'>",
    ]

    parts += [
        "<li><span class='emoji'>🎓</span> – {}</li>".format(instructor),
        "<li><span class='emoji'>🛩️</span> – {}</li>".format(towpilot),
        "<li><span class='emoji'>📋</span> – {}</li>".format(duty_officer),
        "<li><span class='emoji'>💪</span> – "
        "{}</li>".format(assistant_duty_officer),
        "<li><span class='emoji'>✍️</span> – Secretary</li>",
        "<li><span class='emoji'>💰</span> – Treasurer</li>",
        "<li><span class='emoji'>🌐</span> – Webmaster</li>",
        "<li><span class='emoji'>🎩</span> – Director</li>",
        "<li><span class='emoji'>📇</span> – Membership Manager</li>",
    ]

    parts += [
        "</ul>",
        "</div>",
        "</div>",
        "</div>",
        "</div>",
    ]

    return mark_safe("".join(parts))


@register.filter
def render_duties(member):
    duties = []
    from siteconfig.models import SiteConfiguration

    config = SiteConfiguration.objects.first()
    instructor = (
        getattr(config, "instructor_title", "Instructor") if config else "Instructor"
    )
    towpilot = getattr(config, "towpilot_title", "Tow Pilot") if config else "Tow Pilot"
    duty_officer = (
        getattr(config, "duty_officer_title", "Duty Officer")
        if config
        else "Duty Officer"
    )
    assistant_duty_officer = (
        getattr(config, "assistant_duty_officer_title", "Assistant Duty Officer")
        if config
        else "Assistant Duty Officer"
    )
    if member.instructor:
        duties.append(f'<span title="{instructor}" class="emoji">🎓</span>')
    if member.towpilot:
        # Append tow pilot emoji to duties instead of returning the legend here.
        # The legend is built once later and returned if no duties are present.
        duties.append(f'<span title="{towpilot}" class="emoji">🛩️</span>')
    # assistant_duty_officer already set above; no need to repeat it
    # Return inline duty icons for the member, or a short fallback message.
    if duties:
        return mark_safe(" ".join(duties))
    # No duties for this member; show a gentle placeholder.
    return mark_safe("<em>None assigned</em>")

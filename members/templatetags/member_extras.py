# ya know, sometimes, I don't want to construct a person's name from all these fields.
# This is a small template filter that will display a member's name in a more human-readable format.
# I wish people would be simple with a first name and a last name. Why do they have to be all difficult
# with name suffixes, and middle initials, and nicknames? 😂


from django import template
import re
from django.utils.safestring import mark_safe


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
    from django.template.loader import render_to_string
    if member.instructor:
        duties.append(
            f'<span title="{{% get_siteconfig as config %}}{{{{ config.instructor_title|default:"Instructor" }}}}" class="emoji">🎓</span>')
    if member.towpilot:
        duties.append(
            f'<span title="{{% get_siteconfig as config %}}{{{{ config.towpilot_title|default:"Tow Pilot" }}}}" class="emoji">🛩️</span>')
    if member.duty_officer:
        duties.append(
            f'<span title="{{% get_siteconfig as config %}}{{{{ config.duty_officer_title|default:"Duty Officer" }}}}" class="emoji">📋</span>')
    if member.assistant_duty_officer:
        duties.append(
            f'<span title="{{% get_siteconfig as config %}}{{{{ config.assistant_duty_officer_title|default:"Assistant Duty Officer" }}}}" class="emoji">💪</span>')
    if member.secretary:
        duties.append('<span title="Secretary" class="emoji">✍️</span>')
    if member.treasurer:
        duties.append('<span title="Treasurer" class="emoji">💰</span>')
    if member.webmaster:
        duties.append('<span title="Webmaster" class="emoji">🌐</span>')
    if member.director:
        duties.append('<span title="Director" class="emoji"️>🎩</span>')
    if member.member_manager:
        duties.append(
            '<span title="Membership Manager" class="emoji">📇</span>')

    return ' '.join(duties) if duties else "-"


@register.filter
def pluck_ids(members):
    return [str(member.pk) for member in members]


@register.simple_tag
def duty_emoji_legend():
    return mark_safe("""
        <div class="accordion mb-4" id="emojiLegendAccordion">
            <div class="accordion-item">
                <h2 class="accordion-header" id="headingLegend">
                    <button class="accordion-button collapsed" type="button" data-bs-toggle="collapse" data-bs-target="#collapseLegend" aria-expanded="false" aria-controls="collapseLegend">
                        📖 Expand to show Legend 
                    </button>
                </h2>
                <div id="collapseLegend" class="accordion-collapse collapse" aria-labelledby="headingLegend" data-bs-parent="#emojiLegendAccordion">
                    <div class="accordion-body">
                        <ul class="list-unstyled mb-0">
                            <li><span class="emoji">🎓</span> – {{% get_siteconfig as config %}}{{ config.instructor_title|default:"Instructor" }}</li>
                            <li><span class="emoji">🛩️</span> – {{% get_siteconfig as config %}}{{ config.towpilot_title|default:"Tow Pilot" }}</li>
                            <li><span class="emoji">📋</span> – {{% get_siteconfig as config %}}{{ config.duty_officer_title|default:"Duty Officer" }}</li>
                            <li><span class="emoji">💪</span> – {{% get_siteconfig as config %}}{{ config.assistant_duty_officer_title|default:"Assistant Duty Officer" }}</li>
                            <li><span class="emoji">✍️</span> – Secretary</li>
                            <li><span class="emoji">💰</span> – Treasurer</li>
                            <li><span class="emoji">🌐</span> – Webmaster</li>
                            <li><span class="emoji">🎩</span> – Director</li>
                            <li><span class="emoji">📇</span> – Membership Manager</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
        """)

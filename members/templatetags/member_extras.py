# ya know, sometimes, I don't want to construct a person's name from all these fields.
# This is a small template filter that will display a member's name in a more human-readable format.
# I wish people would be simple with a first name and a last name. Why do they have to be all difficult
# with name suffixes, and middle initials, and nicknames? 😂


import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from members.utils.kiosk import is_kiosk_session as check_kiosk_session
from siteconfig.models import SiteConfiguration

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
        duties.append(
            f'<span class="badge bg-primary me-1" title="{instructor}"><i class="bi bi-mortarboard"></i> {instructor}</span>'
        )
    if member.towpilot:
        duties.append(
            f'<span class="badge bg-success me-1" title="{towpilot}"><i class="bi bi-airplane"></i> {towpilot}</span>'
        )
    if member.duty_officer:
        duties.append(
            f'<span class="badge bg-warning text-dark me-1" title="{duty_officer}"><i class="bi bi-clipboard-check"></i> {duty_officer}</span>'
        )
    if member.assistant_duty_officer:
        duties.append(
            f'<span class="badge bg-info me-1" title="{assistant_duty_officer}"><i class="bi bi-person-check"></i> {assistant_duty_officer}</span>'
        )
    if member.secretary:
        duties.append(
            '<span class="badge bg-secondary me-1" title="Secretary"><i class="bi bi-pen"></i> Secretary</span>'
        )
    if member.treasurer:
        duties.append(
            '<span class="badge bg-success me-1" title="Treasurer"><i class="bi bi-cash-coin"></i> Treasurer</span>'
        )
    if member.webmaster:
        duties.append(
            '<span class="badge bg-dark me-1" title="Webmaster"><i class="bi bi-globe"></i> Webmaster</span>'
        )
    if member.director:
        duties.append(
            '<span class="badge bg-danger me-1" title="Director"><i class="bi bi-person-badge"></i> Director</span>'
        )
    if member.member_manager:
        duties.append(
            '<span class="badge bg-purple me-1" title="Membership Manager"><i class="bi bi-person-rolodex"></i> Member Manager</span>'
        )

    return (
        " ".join(duties)
        if duties
        else '<span class="text-muted fst-italic">None assigned</span>'
    )


@register.filter
def pluck_ids(members):
    """Extract member IDs from a collection of members"""
    # Check if it's a single Django model instance
    if hasattr(members, "_meta"):  # _meta is specific to Django model instances
        return [str(members.pk)]
    # Check if it's an iterable collection but not a string
    elif hasattr(members, "__iter__") and not isinstance(members, str):
        try:
            return [str(member.pk) for member in members]
        except TypeError:
            return []
    return []


@register.filter
def member_roles(member):
    """Extract role information from a single member for search/filtering"""
    roles = []
    if member.instructor:
        roles.append("instructor")
    if member.towpilot:
        roles.append("towpilot")
    if member.duty_officer:
        roles.append("duty_officer")
    if member.assistant_duty_officer:
        roles.append("assistant_duty_officer")
    if member.director:
        roles.append("director")
    if member.member_manager:
        roles.append("member_manager")
    if member.webmaster:
        roles.append("webmaster")
    if member.treasurer:
        roles.append("treasurer")
    if member.secretary:
        roles.append("secretary")
    return " ".join(roles)


@register.simple_tag
def duty_badge_legend():
    # Get the first SiteConfiguration object with caching, or use defaults if not found
    from django.core.cache import cache

    config = cache.get("site_configuration")
    if config is None:
        config = SiteConfiguration.objects.first()
        # Cache for 1 hour since site configuration rarely changes
        cache.set("site_configuration", config, 3600)
    # Escape dynamic content to prevent XSS
    instructor = escape(
        getattr(config, "instructor_title", "Instructor") if config else "Instructor"
    )
    towpilot = escape(
        getattr(config, "towpilot_title", "Tow Pilot") if config else "Tow Pilot"
    )
    duty_officer = escape(
        getattr(config, "duty_officer_title", "Duty Officer")
        if config
        else "Duty Officer"
    )
    assistant_duty_officer = escape(
        getattr(config, "assistant_duty_officer_title", "Assistant Duty Officer")
        if config
        else "Assistant Duty Officer"
    )
    # Dynamic content is properly escaped above - safe to use mark_safe
    return mark_safe(  # nosec B308,B703
        f"""
        <div class='accordion mb-4' id='badgeLegendAccordion'>
            <div class='accordion-item'>
                <h2 class='accordion-header' id='headingLegend'>
                    <button class='accordion-button collapsed' type='button' data-bs-toggle='collapse' data-bs-target='#collapseLegend' aria-expanded='false' aria-controls='collapseLegend'>
                        <i class="bi bi-info-circle me-2"></i> Role Badge Legend
                    </button>
                </h2>
                <div id='collapseLegend' class='accordion-collapse collapse' aria-labelledby='headingLegend' data-bs-parent='#badgeLegendAccordion'>
                    <div class='accordion-body'>
                        <div class='row g-3'>
                            <div class='col-md-6'>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-primary me-3'><i class='bi bi-mortarboard'></i> {instructor}</span>
                                    <small class='text-muted'>Flight training</small>
                                </div>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-success me-3'><i class='bi bi-airplane'></i> {towpilot}</span>
                                    <small class='text-muted'>Aircraft operations</small>
                                </div>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-warning text-dark me-3'><i class='bi bi-clipboard-check'></i> {duty_officer}</span>
                                    <small class='text-muted'>Daily operations</small>
                                </div>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-info me-3'><i class='bi bi-person-check'></i> {assistant_duty_officer}</span>
                                    <small class='text-muted'>Assistant operations</small>
                                </div>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-secondary me-3'><i class='bi bi-pen'></i> Secretary</span>
                                    <small class='text-muted'>Club administration</small>
                                </div>
                            </div>
                            <div class='col-md-6'>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-success me-3'><i class='bi bi-cash-coin'></i> Treasurer</span>
                                    <small class='text-muted'>Financial management</small>
                                </div>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-dark me-3'><i class='bi bi-globe'></i> Webmaster</span>
                                    <small class='text-muted'>Website management</small>
                                </div>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-danger me-3'><i class='bi bi-person-badge'></i> Director</span>
                                    <small class='text-muted'>Board member</small>
                                </div>
                                <div class='d-flex align-items-center mb-2'>
                                    <span class='badge bg-purple me-3'><i class='bi bi-person-rolodex'></i> Member Manager</span>
                                    <small class='text-muted'>Membership management</small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """
    )


# Keep the old function name for backward compatibility
@register.simple_tag
def duty_emoji_legend():
    """
    DEPRECATED: This is a backward compatibility wrapper for legacy templates.
    Please migrate to `duty_badge_legend` in future template updates.
    """
    return duty_badge_legend()


@register.simple_tag(takes_context=True)
def can_view_personal_info_tag(context, member):
    """Template tag wrapper for members.utils.can_view_personal_info.

    Usage: {% if can_view_personal_info_tag member %} ... {% endif %}
    """
    from members.utils import can_view_personal_info

    request = context.get("request")
    user = getattr(request, "user", None) if request else None
    return can_view_personal_info(user, member)


@register.simple_tag(takes_context=True)
def is_kiosk_session(context):
    """
    Check if the current session is a kiosk session (Issue #364).

    Returns True if the user was authenticated via kiosk token by the
    KioskAutoLoginMiddleware, which means we should hide the logout button
    and treat them specially.

    Uses shared utility function from members.utils.kiosk.

    Usage: {% is_kiosk_session as kiosk_mode %}
           {% if not kiosk_mode %}...logout button...{% endif %}
    """
    request = context.get("request")
    if not request:
        return False

    return check_kiosk_session(request)

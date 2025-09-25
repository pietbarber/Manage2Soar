from siteconfig.models import SiteConfiguration


def get_role_title(role):
    config = SiteConfiguration.objects.first()
    if not config:
        # Fallbacks
        return {
            'duty_officer': 'Duty Officer',
            'assistant_duty_officer': 'Assistant Duty Officer',
            'towpilot': 'Tow Pilot',
            'instructor': 'Instructor',
            'surge_towpilot': 'Surge Tow Pilot',
            'surge_instructor': 'Surge Instructor',
        }.get(role, role.replace('_', ' ').title())
    mapping = {
        'duty_officer': config.duty_officer_title,
        'assistant_duty_officer': config.assistant_duty_officer_title,
        'towpilot': config.towpilot_title,
        'instructor': config.instructor_title,
        'surge_towpilot': config.surge_towpilot_title or 'Surge Tow Pilot',
        'surge_instructor': config.surge_instructor_title or 'Surge Instructor',
    }
    return mapping.get(role, role.replace('_', ' ').title())

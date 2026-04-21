from siteconfig.models import SiteConfiguration


def get_role_title(role):
    config = SiteConfiguration.objects.first()
    default_titles = {
        "duty_officer": "Duty Officer",
        "assistant_duty_officer": "Assistant Duty Officer",
        "towpilot": "Tow Pilot",
        "instructor": "Instructor",
        "commercial_pilot": "Commercial Pilot",
        "surge_towpilot": "Surge Tow Pilot",
        "surge_instructor": "Surge Instructor",
    }

    if not config:
        # Fallbacks
        return default_titles.get(role, role.replace("_", " ").title())

    mapping = {
        "duty_officer": config.duty_officer_title,
        "assistant_duty_officer": config.assistant_duty_officer_title,
        "towpilot": config.towpilot_title,
        "instructor": config.instructor_title,
        "commercial_pilot": config.commercial_pilot_title,
        "surge_towpilot": config.surge_towpilot_title or "Surge Tow Pilot",
        "surge_instructor": config.surge_instructor_title or "Surge Instructor",
    }

    # Legacy terminology in Site Configuration always wins for legacy keys.
    if role in mapping:
        return mapping[role]

    # For dynamic roles, resolve display name from role registry when enabled.
    if config.enable_dynamic_duty_roles:
        from duty_roster.models import DutyRoleDefinition

        role_def = DutyRoleDefinition.objects.filter(
            site_configuration=config,
            key=role,
            is_active=True,
        ).first()
        if role_def:
            # If dynamic role maps to a legacy key, keep terminology precedence.
            if role_def.legacy_role_key and role_def.legacy_role_key in mapping:
                return mapping[role_def.legacy_role_key]
            return role_def.display_name

    return mapping.get(role, role.replace("_", " ").title())

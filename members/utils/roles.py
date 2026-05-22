from django.core.cache import cache

from siteconfig.models import SiteConfiguration

SITE_CONFIGURATION_CACHE_KEY = "siteconfig_deferred"
SITE_CONFIGURATION_CACHE_TTL_SECONDS = 60


def _get_cached_site_configuration() -> SiteConfiguration | None:
    # Reuse the existing deferred SiteConfiguration cache pattern so cache
    # invalidation in SiteConfiguration.save()/delete() stays in sync.
    return cache.get_or_set(
        SITE_CONFIGURATION_CACHE_KEY,
        lambda: SiteConfiguration.objects.defer("webcam_snapshot_url").first(),
        SITE_CONFIGURATION_CACHE_TTL_SECONDS,
    )


def get_member_role_metadata(config: SiteConfiguration | None = None):
    if config is None:
        config = _get_cached_site_configuration()

    return [
        {
            "value": "towpilot",
            "field": "towpilot",
            "label": (
                getattr(config, "towpilot_title", "Tow Pilot")
                if config
                else "Tow Pilot"
            ),
            "icon": "bi-airplane",
            "badge_class": "bg-success",
            "show_in_duties": True,
        },
        {
            "value": "instructor",
            "field": "instructor",
            "label": (
                getattr(config, "instructor_title", "Instructor")
                if config
                else "Instructor"
            ),
            "icon": "bi-mortarboard",
            "badge_class": "bg-primary",
            "show_in_duties": True,
        },
        {
            "value": "duty_officer",
            "field": "duty_officer",
            "label": (
                getattr(config, "duty_officer_title", "Duty Officer")
                if config
                else "Duty Officer"
            ),
            "icon": "bi-clipboard-check",
            "badge_class": "bg-warning text-dark",
            "show_in_duties": True,
        },
        {
            "value": "assistant_duty_officer",
            "field": "assistant_duty_officer",
            "label": (
                getattr(
                    config, "assistant_duty_officer_title", "Assistant Duty Officer"
                )
                if config
                else "Assistant Duty Officer"
            ),
            "icon": "bi-person-check",
            "badge_class": "bg-info",
            "show_in_duties": True,
        },
        {
            "value": "director",
            "field": "director",
            "label": "Director",
            "icon": "bi-person-badge",
            "badge_class": "bg-danger",
            "show_in_duties": True,
        },
        {
            "value": "member_manager",
            "field": "member_manager",
            "label": "Member Manager",
            "icon": "bi-person-rolodex",
            "badge_class": "bg-purple",
            "show_in_duties": True,
        },
        {
            "value": "webmaster",
            "field": "webmaster",
            "label": "Webmaster",
            "icon": "bi-globe",
            "badge_class": "bg-dark",
            "show_in_duties": True,
        },
        {
            "value": "secretary",
            "field": "secretary",
            "label": "Secretary",
            "icon": "bi-pen",
            "badge_class": "bg-secondary",
            "show_in_duties": True,
        },
        {
            "value": "treasurer",
            "field": "treasurer",
            "label": "Treasurer",
            "icon": "bi-cash-coin",
            "badge_class": "bg-success",
            "show_in_duties": True,
        },
        {
            "value": "rostermeister",
            "field": "rostermeister",
            "label": "Rostermeister",
            "icon": "bi-calendar-check",
            "badge_class": "bg-info text-dark",
            "show_in_duties": False,
        },
        {
            "value": "safety_officer",
            "field": "safety_officer",
            "label": "Safety Officer",
            "icon": "bi-shield-check",
            "badge_class": "bg-warning text-dark",
            "show_in_duties": False,
        },
    ]

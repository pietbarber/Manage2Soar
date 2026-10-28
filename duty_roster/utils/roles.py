from members.models import Member


def member_is_commercial_pilot(member: Member) -> bool:
    return (getattr(member, "glider_rating", "") or "").lower() == "commercial"


def commercial_duty_enabled(config) -> bool:
    """
    Whether the Commercial Pilot *duty* role is active for the current club.

    The commercial-pilot duty slot is only meaningful when the club both
    enables commercial-ride ticketing/workflows AND schedules commercial
    pilots ahead of time. Clubs that don't run commercial-ride duty (e.g. ssc)
    should not surface a Commercial Pilot "hole to fill" on the duty roster.

    Issue #1129 (un-gated by PR #1121 while fixing #1120).

    :param config: the current ``SiteConfiguration`` instance (or ``None``).
    :return: ``True`` only when both flags are truthy.
    """
    return bool(
        config
        and getattr(config, "commercial_rides_enabled", False)
        and getattr(config, "schedule_commercial_pilots", False)
    )


def member_has_role(member: Member, role: str) -> bool:
    if role == "commercial_pilot":
        return member_is_commercial_pilot(member)
    return bool(getattr(member, role, False))

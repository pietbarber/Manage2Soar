from members.models import Member


def member_is_commercial_pilot(member: Member) -> bool:
    return (getattr(member, "glider_rating", "") or "").lower() == "commercial"


def member_has_role(member: Member, role: str) -> bool:
    if role == "commercial_pilot":
        return member_is_commercial_pilot(member)
    return bool(getattr(member, role, False))

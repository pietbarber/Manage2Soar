from __future__ import annotations

import logging
from typing import Optional

from django.core.exceptions import FieldError
from django.db.models import Q
from django.utils import timezone

from duty_roster.models import (
    DutyAssignment,
    DutyQualificationRequirement,
    DutyRoleDefinition,
    MemberDutyQualification,
)
from duty_roster.utils.roles import member_has_role
from members.models import Member
from siteconfig.models import SiteConfiguration
from siteconfig.utils import get_role_title

logger = logging.getLogger("duty_roster.role_resolution")

DEFAULT_ROLES = tuple(DutyAssignment.LEGACY_ROLE_TO_FIELD.keys())


class RoleResolutionService:
    """Compatibility-first resolver for duty role labels and eligibility."""

    def __init__(self, site_configuration: Optional[SiteConfiguration] = None):
        self.site_configuration = site_configuration

    def _get_site_configuration(self) -> Optional[SiteConfiguration]:
        if self.site_configuration is not None:
            return self.site_configuration
        self.site_configuration = SiteConfiguration.objects.first()
        return self.site_configuration

    def _is_dynamic_enabled(self) -> bool:
        config = self._get_site_configuration()
        return bool(config and config.enable_dynamic_duty_roles)

    def _role_queryset(self):
        config = self._get_site_configuration()
        if not config:
            return DutyRoleDefinition.objects.none()
        return DutyRoleDefinition.objects.filter(site_configuration=config)

    def get_enabled_roles(self) -> list[str]:
        """Return role keys to use for scheduling and UI lists."""
        if self._is_dynamic_enabled():
            dynamic_roles = list(
                self._role_queryset()
                .filter(is_active=True)
                .order_by("sort_order", "display_name")
                .values_list("key", flat=True)
            )
            if dynamic_roles:
                return dynamic_roles

        config = self._get_site_configuration()
        if config:
            scheduled_roles = []
            if config.schedule_instructors:
                scheduled_roles.append("instructor")
            if config.schedule_tow_pilots:
                scheduled_roles.append("towpilot")
            if config.schedule_duty_officers:
                scheduled_roles.append("duty_officer")
            if config.schedule_assistant_duty_officers:
                scheduled_roles.append("assistant_duty_officer")
            if config.schedule_commercial_pilots:
                scheduled_roles.append("commercial_pilot")
            return scheduled_roles
        return list(DEFAULT_ROLES)

    def get_role_label(self, role_key: str) -> str:
        """Resolve display label with Site Configuration terminology precedence."""
        role_definition = None
        if self._is_dynamic_enabled():
            role_definition = (
                self._role_queryset().filter(key=role_key, is_active=True).first()
            )

        # If we have an active dynamic role definition, prefer legacy site
        # terminology when mapped, otherwise the role's display name.
        if role_definition:
            if role_definition.legacy_role_key:
                title = get_role_title(role_definition.legacy_role_key)
                if title:
                    return title
            if role_definition.display_name:
                return role_definition.display_name

        # Fall back to site-level role title or a safe, non-None textual
        # fallback derived from the role key. `get_role_title` may return
        # None if site-config fields are unset, so ensure we always return
        # a plain `str` here to satisfy static type checks.
        title = get_role_title(role_key)
        if title:
            return title
        return (role_key or "").replace("_", " ").title()

    def is_member_eligible(self, member: Member, role_key: str) -> bool:
        """Determine role eligibility, using dynamic requirements when enabled."""
        return member.pk in self.get_eligible_member_ids(
            role_key,
            members_queryset=Member.objects.filter(pk=member.pk),
        )

    def get_eligible_member_ids(self, role_key: str, members_queryset=None) -> set[int]:
        """Return eligible member IDs for a role using set-based DB queries where possible."""
        if members_queryset is None:
            members_queryset = Member.objects.all()

        candidate_ids = set(members_queryset.values_list("id", flat=True))
        if not candidate_ids:
            return set()

        if not self._is_dynamic_enabled():
            return {
                m.id for m in members_queryset if m.id and member_has_role(m, role_key)
            }

        role_definition = (
            self._role_queryset()
            .filter(key=role_key, is_active=True)
            .prefetch_related("qualification_requirements")
            .first()
        )
        if not role_definition:
            return {
                m.id for m in members_queryset if m.id and member_has_role(m, role_key)
            }

        requirements = [
            req
            for req in role_definition.qualification_requirements.all()
            if req.is_required
        ]
        if not requirements:
            fallback_role = role_definition.legacy_role_key or role_key
            return {
                m.id
                for m in members_queryset
                if m.id and member_has_role(m, fallback_role)
            }

        eligible_ids = set(candidate_ids)
        today = timezone.localdate()

        for requirement in requirements:
            requirement_type = requirement.requirement_type
            requirement_value = requirement.requirement_value

            if requirement_type == DutyQualificationRequirement.TYPE_LEGACY_ROLE_FLAG:
                try:
                    matching_ids = set(
                        members_queryset.filter(
                            id__in=eligible_ids,
                            **{requirement_value: True},
                        ).values_list("id", flat=True)
                    )
                except FieldError:
                    logger.warning(
                        "Invalid legacy role flag '%s' for dynamic role '%s'; "
                        "treating requirement as non-matching",
                        requirement_value,
                        role_key,
                    )
                    matching_ids = set()
            elif (
                requirement_type
                == DutyQualificationRequirement.TYPE_LEGACY_GLIDER_RATING
            ):
                matching_ids = set(
                    members_queryset.filter(
                        id__in=eligible_ids,
                        glider_rating__iexact=requirement_value,
                    ).values_list("id", flat=True)
                )
            elif requirement_type == DutyQualificationRequirement.TYPE_MEMBER_DUTY_QUAL:
                matching_ids = set(
                    MemberDutyQualification.objects.filter(
                        member_id__in=eligible_ids,
                        qualification_code=requirement_value,
                        is_qualified=True,
                    )
                    .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
                    .values_list("member_id", flat=True)
                    .distinct()
                )
            else:
                matching_ids = {
                    member.id
                    for member in members_queryset.filter(id__in=eligible_ids)
                    if member.id and self._meets_requirement(member, requirement)
                }

            eligible_ids &= matching_ids
            if not eligible_ids:
                break

        return eligible_ids

    def _meets_requirement(
        self,
        member: Member,
        requirement: DutyQualificationRequirement,
    ) -> bool:
        requirement_type = requirement.requirement_type
        requirement_value = requirement.requirement_value

        if requirement_type == DutyQualificationRequirement.TYPE_LEGACY_ROLE_FLAG:
            return bool(getattr(member, requirement_value, False))

        if requirement_type == DutyQualificationRequirement.TYPE_LEGACY_GLIDER_RATING:
            glider_rating = (getattr(member, "glider_rating", "") or "").lower()
            return glider_rating == requirement_value.lower()

        if requirement_type == DutyQualificationRequirement.TYPE_MEMBER_DUTY_QUAL:
            return (
                MemberDutyQualification.objects.filter(
                    member=member,
                    qualification_code=requirement_value,
                    is_qualified=True,
                )
                .filter(
                    Q(expires_on__isnull=True) | Q(expires_on__gte=timezone.localdate())
                )
                .exists()
            )

        return False

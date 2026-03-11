from datetime import date

import pytest
from django.urls import reverse

from instructors.models import ClubQualificationType, MemberQualification
from members.models import Member
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
def test_member_view_hides_obsolete_qualifications(client):
    MembershipStatus.objects.update_or_create(
        name="Full Member", defaults={"is_active": True}
    )

    member = Member.objects.create_user(
        username="qual_member",
        password="testpass123",
        membership_status="Full Member",
        is_active=True,
        joined_club=date.today(),
    )

    current = ClubQualificationType.objects.create(
        code="CURRENT_QUAL",
        name="Current Qualification",
        is_obsolete=False,
    )
    obsolete = ClubQualificationType.objects.create(
        code="OLD_QUAL",
        name="Old Qualification",
        is_obsolete=True,
    )

    MemberQualification.objects.create(
        member=member,
        qualification=current,
        is_qualified=True,
        date_awarded=date.today(),
    )
    MemberQualification.objects.create(
        member=member,
        qualification=obsolete,
        is_qualified=True,
        date_awarded=date.today(),
    )

    client.force_login(member)
    response = client.get(reverse("members:member_view", args=[member.pk]))

    assert response.status_code == 200
    qualifications = list(response.context["qualifications"])
    codes = {q.qualification.code for q in qualifications}
    assert "CURRENT_QUAL" in codes
    assert "OLD_QUAL" not in codes

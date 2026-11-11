from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from instructors.models import (
    ClubQualificationType,
    GroundInstruction,
    MemberQualification,
    QualificationPermissionGrant,
    TrainingLesson,
)
from members.models import RoleMetadata
from siteconfig.models import MembershipStatus


@pytest.mark.django_db
def test_ground_instruction_endpoint_rechecks_qualification_expiry_and_revocation(
    client,
):
    MembershipStatus.objects.create(name="Ground instruction active", is_active=True)
    user = get_user_model().objects.create_user(
        username="qualified-ground-instructor",
        password="test-password",
        membership_status="Ground instruction active",
    )
    student = get_user_model().objects.create_user(
        username="ground-instruction-student",
        password="test-password",
        membership_status="Ground instruction active",
    )
    TrainingLesson.objects.create(code="1.1", title="Ground lesson", sort_key="00001")

    group = Group.objects.create(name="Ground instruction qualification bundle")
    RoleMetadata.objects.create(
        group=group,
        key="ground_instruction_qualification_bundle",
        display_name=group.name,
        qualification_permission_bundle=True,
    )
    permission = Permission.objects.get(
        content_type=ContentType.objects.get_for_model(GroundInstruction),
        codename="can_manage_ground_instruction",
    )
    group.permissions.add(permission)
    QualificationPermissionGrant.objects.create(group=group, permission=permission)
    qualification = ClubQualificationType.objects.create(
        code="GROUND_INSTRUCTION_TEST",
        name="Ground instruction test qualification",
        permission_group=group,
    )
    record = MemberQualification.objects.create(
        member=user,
        qualification=qualification,
    )

    client.force_login(user)
    url = reverse("instructors:log_ground_instruction")
    response = client.get(url, {"student_id": student.pk})
    assert response.status_code == 200

    record.expiration_date = timezone.localdate() - timedelta(days=1)
    record.save(update_fields=["expiration_date"])
    assert client.get(url, {"student_id": student.pk}).status_code == 403

    record.expiration_date = None
    record.is_qualified = False
    record.save(update_fields=["expiration_date", "is_qualified"])
    assert client.get(url, {"student_id": student.pk}).status_code == 403

    ground_instruction_count = GroundInstruction.objects.count()
    qualification_count = MemberQualification.objects.count()
    response = client.post(
        url,
        {"form_type": "qualification", "student_id": student.pk},
    )
    assert response.status_code == 403
    assert GroundInstruction.objects.count() == ground_instruction_count
    assert MemberQualification.objects.count() == qualification_count

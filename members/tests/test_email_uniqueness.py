import pytest
from django.db import IntegrityError, transaction

from members.models import Member


@pytest.mark.django_db
def test_member_email_is_unique_without_case_sensitivity():
    Member.objects.create_user(username="email_first", email="Pilot@example.com")

    with pytest.raises(IntegrityError), transaction.atomic():
        Member.objects.create_user(username="email_second", email="pilot@EXAMPLE.com")

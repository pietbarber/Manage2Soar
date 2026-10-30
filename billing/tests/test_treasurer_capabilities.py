import pytest
from django.core.exceptions import ValidationError

from billing.permissions import has_billing_access, require_manual_transaction_access
from logsheet.permissions import has_logsheet_finance_access
from members.models import Member


@pytest.fixture
def treasurer(db):
    return Member.objects.create_user(
        username="capability-treasurer",
        treasurer=True,
        membership_status="Full Member",
    )


@pytest.mark.django_db
def test_treasurer_receives_registered_finance_capabilities(treasurer):
    assert treasurer.has_perm("billing.can_manage_billing")
    assert treasurer.has_perm("logsheet.can_manage_logsheet_finances")
    assert treasurer.has_perm("logsheet.can_export_logsheet_finances")
    assert has_billing_access(treasurer)
    assert has_logsheet_finance_access(treasurer)
    assert has_logsheet_finance_access(treasurer, export=True)


@pytest.mark.django_db
def test_non_treasurer_staff_and_ordinary_users_are_denied(db):
    staff = Member.objects.create_user(
        username="finance-staff", is_staff=True, membership_status="Full Member"
    )
    ordinary = Member.objects.create_user(
        username="finance-member", membership_status="Full Member"
    )

    for user in (staff, ordinary):
        assert not has_billing_access(user)
        assert not has_logsheet_finance_access(user)
        with pytest.raises(ValidationError):
            require_manual_transaction_access(user)


@pytest.mark.django_db
def test_inactive_treasurer_is_denied(db):
    inactive = Member.objects.create_user(
        username="inactive-capability-treasurer",
        treasurer=True,
        is_active=False,
        membership_status="Non-Member",
    )
    assert not has_billing_access(inactive)
    assert not has_logsheet_finance_access(inactive)


@pytest.mark.django_db
def test_superuser_keeps_finance_access(db):
    superuser = Member.objects.create_superuser(
        username="finance-superuser", password="test-password"
    )
    assert has_billing_access(superuser)
    assert has_logsheet_finance_access(superuser)
    assert has_logsheet_finance_access(superuser, export=True)

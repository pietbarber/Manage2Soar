from django.core.exceptions import ValidationError

from members.utils.membership import is_active_member

BILLING_PERMISSION = "billing.can_manage_billing"


def has_billing_access(actor):
    """Return whether an active club member has the billing capability."""
    if not actor or not getattr(actor, "is_authenticated", False):
        return False
    if not getattr(actor, "is_active", False) or not is_active_member(actor):
        return False
    return bool(actor.is_superuser or actor.has_perm(BILLING_PERMISSION))


def require_manual_transaction_access(actor):
    """Require the registered billing capability for staff ledger mutations."""
    if not has_billing_access(actor):
        raise ValidationError(
            "Only treasurers and superusers may post or reverse manual transactions."
        )


def require_audit_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"A {label} is required.")
    return value.strip()

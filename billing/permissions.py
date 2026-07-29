from django.core.exceptions import ValidationError


def require_manual_transaction_access(actor):
    """Require a treasurer or superuser for staff ledger mutations."""
    if actor is None or not (
        getattr(actor, "is_superuser", False) or getattr(actor, "treasurer", False)
    ):
        raise ValidationError(
            "Only treasurers and superusers may post or reverse manual transactions."
        )


def require_audit_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"A {label} is required.")
    return value.strip()

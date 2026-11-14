from django.core.exceptions import ValidationError


class BillingDisabledError(ValidationError):
    """Raised when a disabled site attempts to mutate its billing ledger."""


class ClubAccountingDisabledError(ValidationError):
    """Raised when club books are posted to while club accounting is off."""

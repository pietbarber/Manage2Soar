from django.core.exceptions import ValidationError


class BillingDisabledError(ValidationError):
    """Raised when a disabled site attempts to mutate its billing ledger."""

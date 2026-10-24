from datetime import date
from decimal import Decimal

from django import forms

from billing.services import OPENING_BALANCE_OVERRIDE_MAX_DESCRIPTION


class ManualEntryForm(forms.Form):
    # "Initial debit" and "Initial credit" both post the account's one
    # opening balance; the kind itself carries the debit/credit direction.
    INITIAL_BALANCE_EFFECTS = {
        "initial_debit": "debit",
        "initial_credit": "credit",
    }
    KIND_CHOICES = (
        ("manual_charge", "Manual charge"),
        ("payment", "Payment"),
        ("credit", "General credit"),
        ("initial_debit", "Initial Debit: member owes the club"),
        ("initial_credit", "Initial Credit: member starts with a credit"),
    )

    kind = forms.ChoiceField(choices=KIND_CHOICES)
    amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=12, decimal_places=2
    )
    effective_date = forms.DateField(
        initial=date.today, widget=forms.DateInput(attrs={"type": "date"})
    )
    description = forms.CharField(max_length=255)
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, allow_initial_balance=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not allow_initial_balance:
            self.fields["kind"].choices = [
                choice
                for choice in self.KIND_CHOICES
                if choice[0] not in self.INITIAL_BALANCE_EFFECTS
            ]


class OpeningBalanceOverrideForm(forms.Form):
    EFFECT_CHOICES = (
        ("debit", "Initial Debit: member owes the club"),
        ("credit", "Initial Credit: member starts with a credit"),
    )

    amount = forms.DecimalField(
        min_value=Decimal("0.01"), max_digits=12, decimal_places=2
    )
    effect = forms.ChoiceField(choices=EFFECT_CHOICES)
    effective_date = forms.DateField(
        initial=date.today, widget=forms.DateInput(attrs={"type": "date"})
    )
    # Must stay short enough that the "Opening balance override: " prefix
    # added at posting time still fits LedgerEntry.member_description;
    # derived from the same constant the service layer enforces.
    description = forms.CharField(max_length=OPENING_BALANCE_OVERRIDE_MAX_DESCRIPTION)
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))


class ReverseEntryForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))


class GuestRemittanceForm(forms.Form):
    reference = forms.CharField(
        required=False,
        max_length=100,
        help_text="Optional deposit, check, or Zelle confirmation reference.",
    )

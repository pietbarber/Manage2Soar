from datetime import date
from decimal import Decimal

from django import forms


class ManualEntryForm(forms.Form):
    KIND_CHOICES = (
        ("manual_charge", "Manual charge"),
        ("payment", "Payment"),
        ("credit", "General credit"),
        ("opening_balance", "Opening balance"),
    )
    EFFECT_CHOICES = (
        ("debit", "Debit: member owes the club"),
        ("credit", "Credit: member has a credit"),
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
    effect = forms.ChoiceField(choices=EFFECT_CHOICES, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == "opening_balance" and not cleaned.get("effect"):
            self.add_error(
                "effect", "Choose whether the opening balance is a debit or credit."
            )
        return cleaned


class ReverseEntryForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))

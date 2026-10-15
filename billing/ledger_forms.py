from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from billing.models import Account, JournalEntry
from siteconfig.timezone_utils import get_club_today

AMOUNT_FIELD = dict(min_value=Decimal("0.01"), max_digits=12, decimal_places=2)


def _date_field(**kwargs):
    return forms.DateField(
        initial=get_club_today, widget=forms.DateInput(attrs={"type": "date"}), **kwargs
    )


def cash_accounts():
    return Account.objects.filter(is_active=True, is_cash=True)


def postable_accounts():
    """Accounts a treasurer may post to directly (never Member Receivables)."""
    return Account.objects.filter(is_active=True).exclude(
        system_role=Account.Role.MEMBER_RECEIVABLES
    )


class _EntryDetailsForm(forms.Form):
    """Fields shared by every club-books entry form."""

    date = _date_field()
    memo = forms.CharField(max_length=255, label="Description")
    reference = forms.CharField(
        max_length=100,
        required=False,
        help_text="Check number, invoice, or confirmation number.",
    )
    internal_note = forms.CharField(
        required=False,
        label="Internal note",
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class ExpenseForm(_EntryDetailsForm):
    paid_from = forms.ModelChoiceField(queryset=Account.objects.none())
    expense_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), label="Category"
    )
    amount = forms.DecimalField(**AMOUNT_FIELD)
    payee = forms.CharField(max_length=150, required=False, label="Paid to")

    field_order = (
        "date",
        "payee",
        "expense_account",
        "amount",
        "paid_from",
        "memo",
        "reference",
        "internal_note",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["paid_from"].queryset = cash_accounts()
        self.fields["expense_account"].queryset = Account.objects.filter(
            is_active=True, type=Account.Type.EXPENSE
        )


class IncomeForm(_EntryDetailsForm):
    deposit_to = forms.ModelChoiceField(queryset=Account.objects.none())
    income_account = forms.ModelChoiceField(
        queryset=Account.objects.none(), label="Category"
    )
    amount = forms.DecimalField(**AMOUNT_FIELD)
    payee = forms.CharField(max_length=150, required=False, label="Received from")

    field_order = (
        "date",
        "payee",
        "income_account",
        "amount",
        "deposit_to",
        "memo",
        "reference",
        "internal_note",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["deposit_to"].queryset = cash_accounts()
        self.fields["income_account"].queryset = Account.objects.filter(
            is_active=True, type=Account.Type.INCOME
        )


class TransferForm(_EntryDetailsForm):
    from_account = forms.ModelChoiceField(queryset=Account.objects.none(), label="From")
    to_account = forms.ModelChoiceField(queryset=Account.objects.none(), label="To")
    amount = forms.DecimalField(**AMOUNT_FIELD)

    field_order = (
        "date",
        "from_account",
        "to_account",
        "amount",
        "memo",
        "reference",
        "internal_note",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["from_account"].queryset = cash_accounts()
        self.fields["to_account"].queryset = cash_accounts()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("from_account") and cleaned.get("from_account") == cleaned.get(
            "to_account"
        ):
            raise ValidationError("Choose two different accounts.")
        return cleaned


class JournalHeaderForm(_EntryDetailsForm):
    payee = forms.CharField(max_length=150, required=False)

    field_order = ("date", "memo", "payee", "reference", "internal_note")


class JournalLineForm(forms.Form):
    account = forms.ModelChoiceField(queryset=Account.objects.none(), required=False)
    debit = forms.DecimalField(required=False, **AMOUNT_FIELD)
    credit = forms.DecimalField(required=False, **AMOUNT_FIELD)
    memo = forms.CharField(max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = postable_accounts()

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get("account")
        debit, credit = cleaned.get("debit"), cleaned.get("credit")
        if not account and not debit and not credit:
            return cleaned
        if not account:
            raise ValidationError("Choose an account for this line.")
        if bool(debit) == bool(credit):
            raise ValidationError("Enter a debit or a credit, not both.")
        return cleaned


class BaseJournalLineFormSet(forms.BaseFormSet):
    def filled_lines(self):
        return [
            form.cleaned_data
            for form in self.forms
            if form.cleaned_data and form.cleaned_data.get("account")
        ]

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        lines = self.filled_lines()
        if len(lines) < 2:
            raise ValidationError("Enter at least two lines.")
        debit = sum((line.get("debit") or 0 for line in lines), Decimal("0"))
        credit = sum((line.get("credit") or 0 for line in lines), Decimal("0"))
        if debit != credit:
            raise ValidationError(
                f"Debits (${debit:.2f}) must equal credits (${credit:.2f})."
            )


JournalLineFormSet = forms.formset_factory(
    JournalLineForm, formset=BaseJournalLineFormSet, extra=4, max_num=30
)


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ("code", "name", "type", "is_cash", "is_active", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = self.instance
        if instance.pk and (instance.system_role or instance.lines.exists()):
            self.fields["type"].disabled = True
            self.fields["type"].help_text = (
                "Locked: system accounts and accounts with entries keep their type."
            )
        if instance.system_role:
            self.fields["is_active"].disabled = True


class ReverseJournalForm(forms.Form):
    date = _date_field()
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}))


class ClubLedgerFilterForm(forms.Form):
    start = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    end = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    account = forms.ModelChoiceField(
        queryset=Account.objects.all(), required=False, empty_label="All accounts"
    )
    source = forms.ChoiceField(
        choices=(("", "All sources"),) + tuple(JournalEntry.Source.choices),
        required=False,
    )
    q = forms.CharField(required=False, label="Search")

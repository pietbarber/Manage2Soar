from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Ledger(models.Model):
    """The immutable financial history belonging to one member."""

    member = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="billing_ledger",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Billing ledger for {self.member}"

    @property
    def balance(self):
        from billing.services import get_balance

        return get_balance(self)


class LedgerEntry(models.Model):
    class Kind(models.TextChoices):
        FLIGHT_CHARGE = "flight_charge", "Flight charge"
        MISC_CHARGE = "misc_charge", "Miscellaneous charge"
        MANUAL_CHARGE = "manual_charge", "Manual charge"
        PAYMENT = "payment", "Payment"
        CREDIT = "credit", "Credit"
        OPENING_BALANCE = "opening_balance", "Opening balance"
        REVERSAL = "reversal", "Reversal"

    class Effect(models.TextChoices):
        DEBIT = "debit", "Debit"
        CREDIT = "credit", "Credit"

    ledger = models.ForeignKey(
        Ledger,
        on_delete=models.PROTECT,
        related_name="entries",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices)
    effect = models.CharField(max_length=6, choices=Effect.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    effective_date = models.DateField()
    member_description = models.CharField(max_length=255)
    internal_note = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_billing_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    source_key = models.CharField(max_length=160, blank=True, null=True)
    reverses = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="reversal",
    )

    class Meta:
        ordering = ("effective_date", "created_at", "id")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="billing_entry_amount_positive",
            ),
            models.UniqueConstraint(
                fields=("source_key",),
                condition=models.Q(source_key__isnull=False),
                name="billing_entry_source_key_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind__in=(
                            "flight_charge",
                            "misc_charge",
                            "manual_charge",
                        ),
                        effect="debit",
                    )
                    | models.Q(
                        kind__in=("payment", "credit"),
                        effect="credit",
                    )
                    | models.Q(kind="opening_balance")
                    | models.Q(kind="reversal")
                ),
                name="billing_entry_kind_effect_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(kind="reversal") | models.Q(reverses__isnull=False),
                name="billing_reversal_has_original",
            ),
        ]
        indexes = [
            models.Index(
                fields=("ledger", "effective_date", "created_at", "id"),
                name="billing_entry_statement_idx",
            ),
            models.Index(fields=("kind",), name="billing_entry_kind_idx"),
        ]

    def clean(self):
        super().clean()
        debit_kinds = {
            self.Kind.FLIGHT_CHARGE,
            self.Kind.MISC_CHARGE,
            self.Kind.MANUAL_CHARGE,
        }
        credit_kinds = {self.Kind.PAYMENT, self.Kind.CREDIT}
        if self.kind in debit_kinds and self.effect != self.Effect.DEBIT:
            raise ValidationError("Charge entries must be debits.")
        if self.kind in credit_kinds and self.effect != self.Effect.CREDIT:
            raise ValidationError("Payment and credit entries must be credits.")
        if self.kind == self.Kind.REVERSAL and not self.reverses_id:
            raise ValidationError("A reversal must identify the original entry.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Posted billing entries cannot be edited.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Posted billing entries cannot be deleted.")

    @property
    def signed_amount(self):
        if self.effect == self.Effect.CREDIT:
            return -self.amount
        return self.amount

    def __str__(self):
        return f"{self.get_kind_display()}: {self.amount}"

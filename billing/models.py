from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SnapshotManager(models.Manager):
    def bulk_create(self, *args, **kwargs):
        raise ValidationError(
            "Flight charge snapshots must be created through the billing service."
        )


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


class BillingPeriod(models.Model):
    """The mutable closed/open state for one calendar billing month."""

    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("year", "month"), name="billing_period_unique_month"
            ),
            models.CheckConstraint(
                condition=models.Q(month__gte=1, month__lte=12),
                name="billing_period_month_valid",
            ),
        ]
        ordering = ("-year", "-month")

    def __str__(self):
        return (
            f"{self.year}-{self.month:02d} ({'closed' if self.is_closed else 'open'})"
        )


class BillingPeriodEvent(models.Model):
    class Action(models.TextChoices):
        CLOSED = "closed", "Closed"
        REOPENED = "reopened", "Reopened"

    period = models.ForeignKey(
        BillingPeriod, on_delete=models.CASCADE, related_name="events"
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    reason = models.TextField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_period_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")


class LedgerEntry(models.Model):
    class Kind(models.TextChoices):
        FLIGHT_CHARGE = "flight_charge", "Flight charge"
        MISC_CHARGE = "misc_charge", "Miscellaneous charge"
        MANUAL_CHARGE = "manual_charge", "Manual charge"
        PAYMENT = "payment", "Payment"
        CREDIT = "credit", "Credit"
        OPENING_BALANCE = "opening_balance", "Opening balance"
        GUEST_PAYMENT_PENDING = "guest_payment_pending", "Guest payment pending"
        GUEST_REMITTANCE = "guest_remittance", "Guest payment remittance"
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
    correction_group = models.UUIDField(blank=True, null=True, db_index=True)
    flight = models.ForeignKey(
        "logsheet.Flight",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="billing_entries",
    )
    reverses = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="reversal",
    )
    remits = models.OneToOneField(
        "self",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="remittance",
    )
    guest_name = models.CharField(max_length=150, blank=True)
    payment_method = models.CharField(
        max_length=10,
        choices=(
            ("cash", "Cash"),
            ("check", "Check"),
            ("zelle", "Zelle"),
        ),
        blank=True,
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
            models.UniqueConstraint(
                fields=("ledger",),
                condition=models.Q(kind="opening_balance"),
                name="billing_one_opening_balance_per_ledger",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        kind__in=(
                            "flight_charge",
                            "misc_charge",
                            "manual_charge",
                            "guest_payment_pending",
                        ),
                        effect="debit",
                    )
                    | models.Q(
                        kind__in=("payment", "credit", "guest_remittance"),
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
            models.CheckConstraint(
                condition=~models.Q(kind="flight_charge")
                | models.Q(flight__isnull=False),
                name="billing_flight_charge_has_flight",
            ),
            models.CheckConstraint(
                condition=~models.Q(kind="guest_remittance")
                | models.Q(remits__isnull=False),
                name="billing_guest_remittance_has_collection",
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
        if self.kind == self.Kind.GUEST_PAYMENT_PENDING:
            if self.effect != self.Effect.DEBIT:
                raise ValidationError("Pending guest payments must be debits.")
            if not self.guest_name.strip():
                raise ValidationError("A guest name is required.")
            if not self.payment_method:
                raise ValidationError("A guest payment method is required.")
        if self.kind == self.Kind.GUEST_REMITTANCE:
            if self.effect != self.Effect.CREDIT:
                raise ValidationError("Guest remittances must be credits.")
            if not self.remits_id:
                raise ValidationError(
                    "A guest remittance must identify its collection."
                )
            collection = self.remits
            if collection.kind != self.Kind.GUEST_PAYMENT_PENDING:
                raise ValidationError("A remittance must clear a guest payment.")
            if collection.ledger_id != self.ledger_id:
                raise ValidationError("A remittance must use the collection ledger.")
            if collection.amount != self.amount:
                raise ValidationError("Guest remittance must be for the full amount.")
        if self.kind in debit_kinds and self.effect != self.Effect.DEBIT:
            raise ValidationError("Charge entries must be debits.")
        if self.kind in credit_kinds and self.effect != self.Effect.CREDIT:
            raise ValidationError("Payment and credit entries must be credits.")
        if self.kind == self.Kind.REVERSAL and not self.reverses_id:
            raise ValidationError("A reversal must identify the original entry.")
        if self.kind == self.Kind.FLIGHT_CHARGE and not self.flight_id:
            raise ValidationError("Flight charges must identify a flight.")
        if self.kind == self.Kind.REVERSAL:
            if not getattr(self, "_service_created", False):
                raise ValidationError(
                    "Reversals must be created through billing services."
                )
            original = self.reverses
            if original.ledger_id != self.ledger_id:
                raise ValidationError("A reversal must use the original ledger.")
            if original.amount != self.amount:
                raise ValidationError("A reversal must match the original amount.")
            if original.effect == self.effect:
                raise ValidationError("A reversal must have the opposite effect.")

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


class FlightChargeSnapshot(models.Model):
    """Frozen Logsheet allocation evidence for a posted flight charge."""

    ledger_entry = models.OneToOneField(
        LedgerEntry,
        on_delete=models.PROTECT,
        related_name="flight_snapshot",
    )
    flight = models.ForeignKey("logsheet.Flight", on_delete=models.PROTECT)
    billed_member = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT
    )
    tow_amount = models.DecimalField(max_digits=12, decimal_places=2)
    rental_amount = models.DecimalField(max_digits=12, decimal_places=2)
    instruction_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    allocation_rule = models.CharField(max_length=50)
    allocation_version = models.PositiveIntegerField()
    allocation_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = SnapshotManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(tow_amount__gte=0)
                    & models.Q(rental_amount__gte=0)
                    & models.Q(instruction_amount__gte=0)
                    & models.Q(total_amount__gt=0)
                ),
                name="billing_snapshot_amounts_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    tow_amount=models.F("total_amount")
                    - models.F("rental_amount")
                    - models.F("instruction_amount")
                ),
                name="billing_snapshot_components_equal_total",
            ),
        ]

    def clean(self):
        super().clean()
        if self.ledger_entry_id and self.total_amount != self.ledger_entry.amount:
            raise ValidationError("Snapshot total must match the ledger entry amount.")
        if not self.ledger_entry_id:
            raise ValidationError("A snapshot must identify a ledger entry.")
        entry = self.ledger_entry
        if entry.kind != LedgerEntry.Kind.FLIGHT_CHARGE:
            raise ValidationError("Snapshots require a flight charge entry.")
        if entry.ledger.member_id != self.billed_member_id:
            raise ValidationError("Snapshot member must match the ledger member.")
        if entry.flight_id != self.flight_id:
            raise ValidationError("Snapshot flight must match the ledger entry flight.")
        if (
            self.tow_amount + self.rental_amount + self.instruction_amount
            != self.total_amount
        ):
            raise ValidationError("Snapshot components must equal the total amount.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Flight charge snapshots cannot be edited.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Flight charge snapshots cannot be deleted.")

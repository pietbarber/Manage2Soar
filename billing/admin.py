from django.contrib import admin

from billing.models import (
    Account,
    BillingPeriod,
    BillingPeriodEvent,
    FlightChargeSnapshot,
    JournalEntry,
    JournalLine,
    Ledger,
    LedgerEntry,
)


@admin.register(Ledger)
class LedgerAdmin(admin.ModelAdmin):
    list_display = ("member", "created_at")
    search_fields = ("member__username", "member__first_name", "member__last_name")
    readonly_fields = ("member", "created_at")


@admin.register(BillingPeriod)
class BillingPeriodAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "is_closed")
    list_filter = ("is_closed", "year")
    readonly_fields = ("year", "month", "is_closed")


@admin.register(BillingPeriodEvent)
class BillingPeriodEventAdmin(admin.ModelAdmin):
    list_display = ("period", "action", "actor", "created_at")
    list_filter = ("action",)
    readonly_fields = tuple(field.name for field in BillingPeriodEvent._meta.fields)


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("ledger", "kind", "effect", "amount", "effective_date")
    list_filter = ("kind", "effect", "effective_date")
    search_fields = ("ledger__member__username", "member_description", "source_key")
    readonly_fields = tuple(field.name for field in LedgerEntry._meta.fields)


@admin.register(FlightChargeSnapshot)
class FlightChargeSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "flight",
        "billed_member",
        "total_amount",
        "allocation_version",
        "created_at",
    )
    list_filter = ("allocation_rule", "allocation_version")
    search_fields = ("flight__id", "billed_member__username")
    readonly_fields = tuple(field.name for field in FlightChargeSnapshot._meta.fields)


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "type", "is_cash", "system_role", "is_active")
    list_filter = ("type", "is_cash", "is_active")
    search_fields = ("code", "name")
    actions = None

    def has_delete_permission(self, request, obj=None):
        return obj is not None and not obj.system_role


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    can_delete = False
    extra = 0
    readonly_fields = ("account", "debit", "credit", "member", "memo")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "date", "memo", "source", "created_by")
    list_filter = ("source", "date")
    search_fields = ("memo", "payee", "reference", "source_key")
    readonly_fields = tuple(field.name for field in JournalEntry._meta.fields)
    inlines = (JournalLineInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

from django.contrib import admin

from billing.models import Ledger, LedgerEntry


@admin.register(Ledger)
class LedgerAdmin(admin.ModelAdmin):
    list_display = ("member", "created_at")
    search_fields = ("member__username", "member__first_name", "member__last_name")
    readonly_fields = ("member", "created_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ("ledger", "kind", "effect", "amount", "effective_date")
    list_filter = ("kind", "effect", "effective_date")
    search_fields = ("ledger__member__username", "member_description", "source_key")
    readonly_fields = tuple(field.name for field in LedgerEntry._meta.fields)

from django.contrib import admin
from .models import DutyDay, DutySlot, MemberBlackout
from .models import DutyPreference, DutyPairing, DutyAvoidance, DutyAssignment, InstructionSlot, DutySwapRequest, DutySwapOffer, OpsIntent

@admin.register(DutyDay)
class DutyDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'notes')
    search_fields = ('notes',)
    ordering = ('date',)

@admin.register(DutySlot)
class DutySlotAdmin(admin.ModelAdmin):
    list_display = ('duty_day', 'role', 'member')
    list_filter = ('role',)
    search_fields = ('member__first_name', 'member__last_name')
    autocomplete_fields = ('member', 'duty_day')
    ordering = ('duty_day', 'role')

@admin.register(MemberBlackout)
class MemberBlackoutAdmin(admin.ModelAdmin):
    list_display = ('member', 'date', 'note')
    search_fields = ('member__first_name', 'member__last_name', 'note')
    list_filter = ('date',)
    autocomplete_fields = ('member',)
    ordering = ('date',)


@admin.register(DutyPreference)
class DutyPreferenceAdmin(admin.ModelAdmin):
    list_display = ("member", "preferred_day", "comment")
    search_fields = ("member__first_name", "member__last_name", "comment")
    list_filter = ("preferred_day",)
    autocomplete_fields = ["member"]

@admin.register(DutyPairing)
class DutyPairingAdmin(admin.ModelAdmin):
    list_display = ("member", "pair_with")
    autocomplete_fields = ["member", "pair_with"]
    search_fields = ("member__first_name", "member__last_name", "pair_with__first_name", "pair_with__last_name")

@admin.register(DutyAvoidance)
class DutyAvoidanceAdmin(admin.ModelAdmin):
    list_display = ("member", "avoid_with")
    autocomplete_fields = ["member", "avoid_with"]
    search_fields = ("member__first_name", "member__last_name", "avoid_with__first_name", "avoid_with__last_name")

@admin.register(DutyAssignment)
class DutyAssignmentAdmin(admin.ModelAdmin):
    list_display = ("date", "location", "duty_officer", "instructor", "tow_pilot", "is_scheduled", "is_confirmed")

@admin.register(InstructionSlot)
class InstructionSlotAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "instructor", "status", "created_at")
    list_filter = ("status",)
    search_fields = (
        "student__first_name", "student__last_name",
        "instructor__first_name", "instructor__last_name",
    )

@admin.register(DutySwapRequest)
class DutySwapRequestAdmin(admin.ModelAdmin):
    list_display = ("original_date", "role", "requester", "is_emergency", "is_fulfilled", "created_at")
    list_filter = ("role", "is_emergency", "is_fulfilled")
    search_fields = ("requester__first_name", "requester__last_name")

@admin.register(DutySwapOffer)
class DutySwapOfferAdmin(admin.ModelAdmin):
    list_display = ("swap_request", "offered_by", "offer_type", "proposed_swap_date", "status", "created_at")
    list_filter = ("offer_type", "status")
    search_fields = (
        "offered_by__first_name", "offered_by__last_name",
        "swap_request__requester__first_name", "swap_request__requester__last_name"
    )

@admin.register(OpsIntent)
class OpsIntentAdmin(admin.ModelAdmin):
    list_display = ("member", "date", "available_as", "glider", "created_at")
    list_filter = ("date",)
    search_fields = ("member__first_name", "member__last_name")

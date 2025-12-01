from django.contrib import admin

from utils.admin_helpers import AdminHelperMixin

from .models import (
    DutyAssignment,
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    DutySwapOffer,
    DutySwapRequest,
    InstructionSlot,
    MemberBlackout,
    OpsIntent,
)


@admin.register(MemberBlackout)
class MemberBlackoutAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("member", "date", "note")
    search_fields = ("member__first_name", "member__last_name", "note")
    list_filter = ("date",)
    autocomplete_fields = ("member",)
    ordering = ("date",)
    admin_helper_message = "<b>Member Blackouts:</b> Mark member unavailability so they are not scheduled during those dates."


@admin.register(DutyPreference)
class DutyPreferenceAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("member", "preferred_day", "comment")
    search_fields = ("member__first_name", "member__last_name", "comment")
    list_filter = ("preferred_day",)
    autocomplete_fields = ["member"]
    admin_helper_message = "<b>Duty Preferences:</b> Members' scheduling preferences and limits — these feed into automated roster generation."


@admin.register(DutyPairing)
class DutyPairingAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("member", "pair_with")
    autocomplete_fields = ["member", "pair_with"]
    search_fields = (
        "member__first_name",
        "member__last_name",
        "pair_with__first_name",
        "pair_with__last_name",
    )
    admin_helper_message = "<b>Pairings:</b> Preferred pairings to bias scheduling so members are often assigned together."


@admin.register(DutyAvoidance)
class DutyAvoidanceAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("member", "avoid_with")
    autocomplete_fields = ["member", "avoid_with"]
    search_fields = (
        "member__first_name",
        "member__last_name",
        "avoid_with__first_name",
        "avoid_with__last_name",
    )
    admin_helper_message = "<b>Avoidances:</b> Members who should not be scheduled to work together. Use sparingly and only when needed."


@admin.register(DutyAssignment)
class DutyAssignmentAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "date",
        "location",
        "duty_officer",
        "instructor",
        "tow_pilot",
        "is_scheduled",
        "is_confirmed",
        "surge_notified",
        "tow_surge_notified",
    )

    admin_helper_message = "<b>Duty Assignments:</b> View and adjust duty rosters; use swap requests to coordinate changes rather than directly editing assigned members."


@admin.register(InstructionSlot)
class InstructionSlotAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("assignment", "student", "instructor", "status", "created_at")
    list_filter = ("status",)
    search_fields = (
        "student__first_name",
        "student__last_name",
        "instructor__first_name",
        "instructor__last_name",
    )
    admin_helper_message = "<b>Instruction Slots:</b> Student/instructor pairings for training flights; use to manage scheduled instruction."


@admin.register(DutySwapRequest)
class DutySwapRequestAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "original_date",
        "role",
        "requester",
        "is_emergency",
        "is_fulfilled",
        "created_at",
    )
    list_filter = ("role", "is_emergency", "is_fulfilled")
    search_fields = ("requester__first_name", "requester__last_name")
    admin_helper_message = "<b>Swap Requests:</b> Members requesting coverage or swaps. Review offers and coordinate responses here."


@admin.register(DutySwapOffer)
class DutySwapOfferAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "swap_request",
        "offered_by",
        "offer_type",
        "proposed_swap_date",
        "status",
        "created_at",
    )
    list_filter = ("offer_type", "status")
    search_fields = (
        "offered_by__first_name",
        "offered_by__last_name",
        "swap_request__requester__first_name",
        "swap_request__requester__last_name",
    )
    admin_helper_message = "<b>Swap Offers:</b> Offers responding to swap requests; accept and track offers here."


@admin.register(OpsIntent)
class OpsIntentAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("member", "date", "available_as_labels", "glider", "created_at")
    list_filter = ("date",)
    search_fields = ("member__first_name", "member__last_name")
    admin_helper_message = (
        "<b>Ops Intents:</b> Members' declared intent to fly (instruction, club, private)."
        " These feed surge detection and tow planning — encourage members to sign up rather than messaging staff."
    )

    @admin.display(description="Planned activities")
    def available_as_labels(self, obj):
        return ", ".join(obj.available_as_labels())

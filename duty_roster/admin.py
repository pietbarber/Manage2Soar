from django.contrib import admin

from utils.admin_helpers import AdminHelperMixin

from .models import (
    DutyAssignment,
    DutyAvoidance,
    DutyPairing,
    DutyPreference,
    DutyRosterMessage,
    DutySwapOffer,
    DutySwapRequest,
    GliderReservation,
    InstructionSlot,
    MemberBlackout,
    OpsIntent,
)


@admin.register(DutyRosterMessage)
class DutyRosterMessageAdmin(AdminHelperMixin, admin.ModelAdmin):
    """Admin for DutyRosterMessage singleton (Issue #551)."""

    list_display = ("get_preview", "is_active", "updated_at", "updated_by")
    readonly_fields = ("updated_at", "updated_by")
    admin_helper_message = (
        "<b>Duty Roster Message:</b> Rich HTML announcement displayed at the top of the duty calendar. "
        "This is a singleton - only one message can exist. Edit via the form below or use the "
        "<a href='/duty_roster/message/edit/'>dedicated editor</a> for a better TinyMCE experience."
    )

    @admin.display(description="Message Preview")
    def get_preview(self, obj):
        """Show a preview of the message content."""
        from django.utils.html import strip_tags

        if obj and obj.content:
            text = strip_tags(obj.content)
            return text[:100] + "..." if len(text) > 100 else text
        return "(empty)"

    def has_add_permission(self, request):
        """Prevent creating multiple instances (singleton pattern)."""
        from .models import DutyRosterMessage

        # Only allow add if no instance exists
        return not DutyRosterMessage.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Allow deletion to reset the message."""
        return True

    class Media:
        """Include TinyMCE for the content field."""

        js = ()
        css = {}


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
        "request_type",
        "is_emergency",
        "status",
        "created_at",
    )
    list_filter = ("role", "is_emergency", "status", "request_type")
    search_fields = ("requester__first_name", "requester__last_name", "notes")
    readonly_fields = ("created_at", "updated_at", "fulfilled_at")
    admin_helper_message = "<b>Swap Requests:</b> Members requesting coverage or swaps. Review offers and coordinate responses here."


@admin.register(DutySwapOffer)
class DutySwapOfferAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "swap_request",
        "offered_by",
        "offer_type",
        "proposed_swap_date",
        "is_blackout_conflict",
        "status",
        "created_at",
    )
    list_filter = ("offer_type", "status", "is_blackout_conflict")
    search_fields = (
        "offered_by__first_name",
        "offered_by__last_name",
        "swap_request__requester__first_name",
        "swap_request__requester__last_name",
    )
    readonly_fields = ("created_at", "responded_at", "is_blackout_conflict")
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


@admin.register(GliderReservation)
class GliderReservationAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = (
        "date",
        "member",
        "glider",
        "reservation_type",
        "time_preference",
        "status",
        "is_trainer_display",
        "created_at",
    )
    list_filter = ("status", "reservation_type", "time_preference", "date")
    search_fields = (
        "member__first_name",
        "member__last_name",
        "glider__competition_number",
        "glider__n_number",
        "purpose",
    )
    autocomplete_fields = ("member", "glider")
    readonly_fields = ("created_at", "updated_at", "cancelled_at")
    date_hierarchy = "date"
    ordering = ("-date",)

    fieldsets = (
        (
            None,
            {
                "fields": ("member", "glider", "date", "status"),
            },
        ),
        (
            "Reservation Details",
            {
                "fields": (
                    "reservation_type",
                    "time_preference",
                    "start_time",
                    "end_time",
                    "purpose",
                ),
            },
        ),
        (
            "Cancellation",
            {
                "fields": ("cancelled_at", "cancellation_reason"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    admin_helper_message = (
        "<b>Glider Reservations:</b> Members can reserve club gliders ahead of time. "
        "Control reservation settings in SiteConfiguration (max per year, enable/disable). "
        "Reservations appear on the duty calendar and in daily ops emails."
    )

    @admin.display(description="Trainer?", boolean=True)
    def is_trainer_display(self, obj):
        return obj.is_trainer

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("member", "glider")

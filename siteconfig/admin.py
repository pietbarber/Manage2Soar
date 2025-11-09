from django.contrib import admin

from utils.admin_helpers import AdminHelperMixin

from .models import MembershipStatus, SiteConfiguration


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(AdminHelperMixin, admin.ModelAdmin):
    def has_add_permission(self, request):
        # Only allow adding if no config exists
        return not SiteConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion
        return False

    def has_change_permission(self, request, obj=None):
        # Only allow Webmaster (superuser or group) to edit
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Webmaster").exists()
        )

    readonly_fields = ("visiting_pilot_token", "visiting_pilot_token_created")
    actions = ["regenerate_visiting_pilot_token"]
    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "club_name",
                    "domain_name",
                    "club_abbreviation",
                    "club_logo",
                    "club_nickname",
                )
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    "contact_welcome_text",
                    "contact_response_info",
                    "club_address_line1",
                    "club_address_line2",
                    "club_city",
                    "club_state",
                    "club_zip_code",
                    "club_country",
                    "club_phone",
                    "operations_info",
                ),
                "description": "Contact form and location information for visitors",
                "classes": ("collapse",),
            },
        ),
        (
            "Scheduling Options",
            {
                "fields": (
                    "schedule_instructors",
                    "schedule_tow_pilots",
                    "schedule_duty_officers",
                    "schedule_assistant_duty_officers",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Role Terminology",
            {
                "fields": (
                    "duty_officer_title",
                    "assistant_duty_officer_title",
                    "towpilot_title",
                    "surge_towpilot_title",
                    "instructor_title",
                    "surge_instructor_title",
                    "membership_manager_title",
                    "equipment_manager_title",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Operational Calendar",
            {
                "fields": (
                    "operations_start_period",
                    "operations_end_period",
                ),
                "description": (
                    "Configure when your club typically operates each year. This affects duty roster generation - "
                    "only weekends within the operational season will be scheduled automatically. "
                    "💡 Examples: 'First weekend of May', '1st weekend of Apr', '2nd weekend Dec', 'Last weekend in October'. "
                    "By default, these fields are pre-filled. To include all dates year-round, delete both values and leave them blank."
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Advanced Options",
            {
                "fields": (
                    "allow_glider_reservations",
                    "allow_two_seater_reservations",
                    "redaction_notification_dedupe_minutes",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Visiting Pilot Management",
            {
                "fields": (
                    "visiting_pilot_enabled",
                    "visiting_pilot_status",
                    "visiting_pilot_welcome_text",
                    "visiting_pilot_require_ssa",
                    "visiting_pilot_require_rating",
                    "visiting_pilot_auto_approve",
                    "visiting_pilot_token",
                    "visiting_pilot_token_created",
                ),
                "description": (
                    "Configure quick signup for visiting pilots. Enable to allow pilots from other clubs "
                    "to register quickly via QR code. Set requirements and membership status assignment. "
                    "The security token makes signup URLs unguessable to prevent spam/abuse."
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.action(description="Regenerate visiting pilot security token")
    def regenerate_visiting_pilot_token(self, request, queryset):
        """Admin action to regenerate visiting pilot security tokens."""
        from django.contrib import messages

        for config in queryset:
            old_token = config.visiting_pilot_token
            new_token = config.refresh_visiting_pilot_token()
            messages.success(
                request,
                f"Regenerated visiting pilot token: {old_token} → {new_token}. "
                f"All existing QR codes and links need to be updated.",
            )

    admin_helper_message = "Site configuration: central site settings. Only the Webmaster should edit these values."


@admin.register(MembershipStatus)
class MembershipStatusAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ("name", "is_active", "sort_order", "created_at")
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "description")
    ordering = ("sort_order", "name")

    fieldsets = (
        (None, {"fields": ("name", "is_active", "sort_order", "description")}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    readonly_fields = ("created_at", "updated_at")

    def has_change_permission(self, request, obj=None):
        # Only allow Webmaster or superuser to edit membership statuses
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Webmasters").exists()
            or request.user.groups.filter(name="Member Managers").exists()
        )

    def has_add_permission(self, request):
        # Only allow Webmaster or superuser to add membership statuses
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Webmasters").exists()
            or request.user.groups.filter(name="Member Managers").exists()
        )

    def has_delete_permission(self, request, obj=None):
        # Only allow Webmaster or superuser to delete membership statuses
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Webmasters").exists()
        )

    def delete_model(self, request, obj):
        """Override delete to check if status is in use by any members."""
        from django.contrib import messages

        from members.models import Member

        member_count = Member.objects.filter(membership_status=obj.name).count()
        if member_count > 0:
            messages.error(
                request,
                f'Cannot delete "{obj.name}" - {member_count} members currently have this status. '
                f"Change their status first, then delete this membership status.",
            )
            return

        super().delete_model(request, obj)
        from django.contrib import messages

        messages.success(
            request, f'Successfully deleted membership status "{obj.name}".'
        )

    def delete_queryset(self, request, queryset):
        """Override bulk delete to check if any statuses are in use."""
        from django.contrib import messages

        from members.models import Member

        for obj in queryset:
            member_count = Member.objects.filter(membership_status=obj.name).count()
            if member_count > 0:
                messages.error(
                    request,
                    f'Cannot delete "{obj.name}" - {member_count} members currently have this status.',
                )
                return

        # If we get here, none are in use
        deleted_names = [obj.name for obj in queryset]
        queryset.delete()
        messages.success(
            request,
            f'Successfully deleted membership statuses: {", ".join(deleted_names)}.',
        )

    admin_helper_message = (
        "Membership Statuses: Configure the available membership statuses for your club. "
        "Active statuses allow members to access member-only features. "
        "Sort order controls the display order in dropdowns (lower numbers first). "
        "⚠️ Be careful when deleting statuses - existing members may be using them!"
    )

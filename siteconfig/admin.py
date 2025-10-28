from django.contrib import admin

from .models import SiteConfiguration, MembershipStatus
from utils.admin_helpers import AdminHelperMixin


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

    readonly_fields = ()
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "club_name",
                    "domain_name",
                    "club_abbreviation",
                    "club_logo",
                    "club_nickname",
                    "schedule_instructors",
                    "schedule_tow_pilots",
                    "schedule_duty_officers",
                    "schedule_assistant_duty_officers",
                    "duty_officer_title",
                    "assistant_duty_officer_title",
                    "towpilot_title",
                    "surge_towpilot_title",
                    "instructor_title",
                    "surge_instructor_title",
                    "membership_manager_title",
                    "equipment_manager_title",
                    "allow_glider_reservations",
                    "allow_two_seater_reservations",
                    "redaction_notification_dedupe_minutes",
                )
            },
        ),
    )

    admin_helper_message = (
        "Site configuration: central site settings. Only the Webmaster should edit these values."
    )


@admin.register(MembershipStatus)
class MembershipStatusAdmin(AdminHelperMixin, admin.ModelAdmin):
    list_display = ('name', 'is_active', 'sort_order', 'created_at')
    list_editable = ('is_active', 'sort_order')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    ordering = ('sort_order', 'name')

    fieldsets = (
        (None, {
            'fields': ('name', 'is_active', 'sort_order', 'description')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    readonly_fields = ('created_at', 'updated_at')

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
        # But be careful - this could break existing member records
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Webmasters").exists()
        )

    admin_helper_message = (
        "Membership Statuses: Configure the available membership statuses for your club. "
        "Active statuses allow members to access member-only features. "
        "Sort order controls the display order in dropdowns (lower numbers first). "
        "⚠️ Be careful when deleting statuses - existing members may be using them!"
    )

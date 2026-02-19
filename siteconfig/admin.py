from django import forms
from django.contrib import admin
from django.utils.html import format_html

from utils.admin_helpers import AdminHelperMixin

from .models import (
    ChargeableItem,
    MailingList,
    MailingListCriterion,
    MembershipStatus,
    SiteConfiguration,
)


class MailingListAdminForm(forms.ModelForm):
    """Custom form with multi-select widget for criteria."""

    criteria_select = forms.MultipleChoiceField(
        choices=MailingListCriterion.choices,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Membership Criteria",
        help_text="Select criteria for list membership. Members matching ANY selected criterion will be included.",
    )

    class Meta:
        model = MailingList
        fields = [
            "name",
            "description",
            "is_active",
            "sort_order",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate criteria_select from the JSON field
        if self.instance and self.instance.pk:
            self.fields["criteria_select"].initial = self.instance.criteria or []

    def _post_clean(self):
        """Copy criteria_select to instance.criteria before model validation."""
        # Copy criteria BEFORE super()._post_clean() runs full_clean()
        if hasattr(self, "cleaned_data"):
            self.instance.criteria = self.cleaned_data.get("criteria_select", [])
        super()._post_clean()

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Criteria already copied in _post_clean, but ensure it's set
        if hasattr(self, "cleaned_data"):
            instance.criteria = self.cleaned_data.get("criteria_select", [])
        if commit:
            instance.save()
        return instance


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
            or request.user.groups.filter(name="Webmasters").exists()
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
                    "canonical_url",
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
                    "use_ortools_scheduler",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Surge Alerts & Instructor Notifications",
            {
                "fields": (
                    "tow_surge_threshold",
                    "instruction_surge_threshold",
                    "instructors_email",
                ),
                "description": (
                    "Configure surge alert thresholds and the email address to notify when a duty "
                    "instructor has too many students. "
                    "<strong>instructors_email</strong> should be set to your instructors mailing "
                    "list address (e.g. instructors@skylinesoaring.org). "
                    "Tow/instruction surge thresholds trigger an alert email to the respective "
                    "mailing lists when ops-intent sign-ups reach or exceed the threshold."
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
            "⚠️ Duty Roster Announcements (DEPRECATED)",
            {
                "fields": ("duty_roster_announcement",),
                "description": (
                    "<strong>⚠️ DEPRECATED:</strong> This field is deprecated as of Issue #551. "
                    "Use the new rich HTML editor in the Duty Roster app instead. "
                    "Rostermeisters can access it via the 'Edit Announcement' button on the duty calendar. "
                    "This field will be removed in a future release. "
                    "NOTE: The URL path should be kept in sync with duty_roster/urls.py."
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
                    "max_reservations_per_year",
                    "max_reservations_per_month",
                    "allow_towplane_rental",
                    "waive_tow_fee_on_retrieve",
                    "waive_rental_fee_on_retrieve",
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
        (
            "Membership Application Settings",
            {
                "fields": (
                    "membership_application_enabled",
                    "membership_application_terms",
                ),
                "description": (
                    "Configure the membership application form. Enable to allow prospective members "
                    "to submit applications online, and set custom terms and conditions. "
                    "Membership applications currently require manual review in the admin."
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Mail Server Configuration",
            {
                "fields": ("manual_whitelist",),
                "description": (
                    "Email whitelist for trusted non-members. Enter one email address per line. "
                    "These addresses can send to mailing lists alongside club members. "
                    "Use for former members, vendors, partners, or other trusted contacts. "
                    "Example: bob@example.com"
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


@admin.register(MailingList)
class MailingListAdmin(AdminHelperMixin, admin.ModelAdmin):
    """Admin interface for managing mailing lists."""

    form = MailingListAdminForm
    list_display = (
        "name",
        "description",
        "is_active",
        "bypass_whitelist",
        "criteria_display",
        "subscriber_count",
        "sort_order",
    )
    list_editable = ("is_active", "bypass_whitelist", "sort_order")
    list_filter = ("is_active", "bypass_whitelist")
    search_fields = ("name", "description")
    ordering = ("sort_order", "name")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "description",
                    "is_active",
                    "sort_order",
                )
            },
        ),
        (
            "Membership Criteria",
            {
                "fields": ("criteria_select",),
                "description": "Select which members should be included in this list. "
                "Members matching ANY selected criterion will be subscribed.",
            },
        ),
        (
            "Whitelist Bypass",
            {
                "fields": ("bypass_whitelist",),
                "description": "⚠️ Enable this to allow mail from ANY sender "
                "(not just club members). Use for service accounts like treasurer@ "
                "or webmaster@ that need to receive external verification emails. "
                "SPF PASS is still required, but spam may get through.",
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

    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Criteria")
    def criteria_display(self, obj):
        """Show criteria as comma-separated list."""
        criteria = obj.get_criteria_display()
        if not criteria:
            return format_html('<span style="color: #999;">None</span>')
        return ", ".join(criteria)

    @admin.display(description="Subscribers")
    def subscriber_count(self, obj):
        """
        Show count of subscribers with link to preview.

        Note: This causes N+1 queries in the admin list view, but this is
        acceptable because: (1) admin has low traffic, (2) mailing lists
        are a small dataset, and (3) criteria are dynamic requiring
        different queries for each list.
        """
        count = obj.get_subscriber_count()
        return format_html(
            '<span title="Click list name to see subscribers">{}</span>', count
        )

    def _has_webmaster_permission(self, request):
        """Check if user has webmaster-level permission."""
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Webmasters").exists()
        )

    def has_change_permission(self, request, obj=None):
        return self._has_webmaster_permission(request)

    def has_add_permission(self, request):
        return self._has_webmaster_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self._has_webmaster_permission(request)

    admin_helper_message = (
        "Mailing Lists: Configure email lists for your club's mail server. "
        "Each list can include members matching one or more criteria (using OR logic). "
        "The API at /members/api/email-lists/ returns subscriber emails for each active list."
    )


@admin.register(ChargeableItem)
class ChargeableItemAdmin(AdminHelperMixin, admin.ModelAdmin):
    """
    Admin interface for managing chargeable items catalog.

    Issue #66: Aerotow retrieve fees
    Issue #413: Miscellaneous charges
    """

    list_display = (
        "name",
        "price_display",
        "unit",
        "allows_decimal_quantity",
        "is_active",
        "sort_order",
    )
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active", "unit")
    search_fields = ("name", "description")
    ordering = ("sort_order", "name")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "price",
                    "unit",
                    "allows_decimal_quantity",
                    "is_active",
                    "sort_order",
                )
            },
        ),
        (
            "Details",
            {
                "fields": ("description",),
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

    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Price")
    def price_display(self, obj):
        """Display price with unit."""
        # Format the price first, then pass to format_html
        # (format_html doesn't support format specifiers like {:.2f})
        formatted_price = f"{obj.price:.2f}"
        if obj.unit == ChargeableItem.UnitType.HOUR:
            return format_html("${}/hour", formatted_price)
        return format_html("${}", formatted_price)

    def _has_webmaster_permission(self, request):
        """Check if user has webmaster-level permission."""
        return (
            request.user.is_superuser
            or request.user.groups.filter(name="Webmasters").exists()
        )

    def has_change_permission(self, request, obj=None):
        return self._has_webmaster_permission(request)

    def has_add_permission(self, request):
        return self._has_webmaster_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self._has_webmaster_permission(request)

    admin_helper_message = (
        "Chargeable Items: Catalog of merchandise and service charges. "
        "Add items like t-shirts, logbooks, or service fees like aerotow retrieves. "
        "For time-based charges (like retrieve tach time), set unit to 'Per Hour' and enable decimal quantities."
    )

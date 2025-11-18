import csv
import logging

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.db import models
from django.http import HttpResponse
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from reversion.admin import VersionAdmin
from tinymce.widgets import TinyMCE

from utils.admin_helpers import AdminHelperMixin

from .models import Badge, Biography, Member, MemberBadge
from .models_applications import MembershipApplication

# --- Register or replace social_django admin entries with helpful admin banners ---
try:
    from django.contrib import admin as django_admin
    from social_django.models import Association, Nonce, UserSocialAuth

    def register_or_replace(model, admin_class):
        """If model is already registered in admin, unregister it first, then register our admin_class."""
        try:
            if model in django_admin.site._registry:
                django_admin.site.unregister(model)
        except Exception as e:
            # If unregister fails for any reason, continue and attempt to register
            logging.warning(f"Failed to unregister model {model}: {e}")
        try:
            django_admin.site.register(model, admin_class)
        except Exception as e:
            # If register fails, don't block app startup
            logging.warning(f"Failed to register admin for model {model}: {e}")

    class UserSocialAuthAdmin(AdminHelperMixin, django_admin.ModelAdmin):
        list_display = ("user", "provider", "uid")
        search_fields = ("user__username", "provider", "uid")
        admin_helper_message = "UserSocialAuth: external account links for members. Review before unlinking."

    class AssociationAdmin(AdminHelperMixin, django_admin.ModelAdmin):
        # Association doesn't always have uniform fields across versions; show a compact repr
        list_display = ("__str__",)
        admin_helper_message = "Association: backend association records for OAuth providers. Edit with care."

    class NonceAdmin(AdminHelperMixin, django_admin.ModelAdmin):
        list_display = ("__str__",)
        admin_helper_message = "Nonce: one-time values used during OAuth handshakes. Typically safe to leave alone."

    register_or_replace(UserSocialAuth, UserSocialAuthAdmin)
    register_or_replace(Association, AssociationAdmin)
    register_or_replace(Nonce, NonceAdmin)
except ImportError as e:
    # social_django may not be available in some environments; skip registrations silently
    logging.info(f"social_django not available, skipping OAuth admin registration: {e}")
    pass

# Custom filter for Active/Not active status


class ActiveStatusFilter(SimpleListFilter):
    title = "Active status"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return (
            ("active", "Active"),
            ("not_active", "Not active"),
        )

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(is_active=True)
        if self.value() == "not_active":
            return queryset.filter(is_active=False)
        return queryset


@admin.register(Biography)
class BiographyAdmin(admin.ModelAdmin):
    list_display = ("member", "updated_at")
    search_fields = ("member__first_name", "member__last_name", "member__email")
    ordering = ("-updated_at",)


#########################
# MemberBadgeAdmin Class

# This class defines the admin interface for the MemberBadge model.
# MemberBadge entries represent specific SSA or club badges awarded to members.

# Extends Django's base ModelAdmin to provide standard editing, filtering,
# and list display capabilities for managing badge records directly.

# Currently uses default behavior with no customizations, but can be extended
# to include list_display, search_fields, filters, or inline editing.


@admin.register(MemberBadge)
class MemberBadgeAdmin(admin.ModelAdmin):
    list_display = ("member", "badge", "date_awarded")
    list_filter = ("badge",)
    search_fields = ("member__first_name", "member__last_name", "badge__name")


#########################
# BadgeAdmin Class

# This class defines the admin interface for the Badge model, which represents
# all possible types of soaring badges that can be awarded to members (e.g., SSA A, B, C,
# club-specific achievements, etc.).

# Admin users can use this interface to create, edit, and manage badge definitions.

# Fields typically include badge name, code, description, and any categorization fields.


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.TextField: {"widget": TinyMCE(attrs={"cols": 80, "rows": 10})},
    }
    search_fields = ["name", "description"]


#########################
# MemberBadgeInline Class

# Inline admin class for editing MemberBadge entries directly within the
# MemberAdmin form. Each MemberBadge links a member to a badge they've earned.

# This inline allows badge assignments to be made while editing a member.

# model: MemberBadge — the linking model between Member and Badge
# extra: Set to 0 to avoid displaying extra empty rows by default


class MemberBadgeInline(admin.TabularInline):
    model = MemberBadge
    extra = 1  # Show one empty row to add a badge
    autocomplete_fields = ["badge"]  # Optional: if you have lots of badges


#########################
# CustomMemberChangeForm Class

# This form is used by the Django admin interface when editing an existing Member.
# It extends Django's built-in UserChangeForm and allows customization of field
# display, validation, and behavior specific to the Member model.


# This form is referenced by MemberAdmin via the 'form' attribute.
class CustomMemberChangeForm(UserChangeForm):
    class Meta:
        model = Member
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "membership_status",
            "instructor",
            "towpilot",
        )


#########################
# CustomMemberCreationForm Class

# This form is used by the Django admin interface when creating a new Member.
# It extends Django's built-in UserCreationForm and adds any custom validation
# or additional fields required by the Member model.

# This form is referenced by MemberAdmin via the 'add_form' attribute.


class CustomMemberCreationForm(UserCreationForm):
    class Meta:
        model = Member
        fields = ("username", "email", "first_name", "last_name")


#########################
# MemberBadgeInline Class

# Inline admin class for displaying and editing related MemberBadge entries
# directly within the MemberAdmin form.

# model: MemberBadge — the related model that stores a member's earned badges
# extra: Sets the number of blank inline forms to display by default (0 = none)


#########################
# MemberAdmin Class

# This class customizes the Django admin interface for the Member model.
# It extends both VersionAdmin (from django-reversion) and UserAdmin to
# provide editable fields, filters, and auditing of all member-related changes.

# add_form: Custom form used when creating a new member
# form: Custom form used when editing an existing member
# model: The Member model associated with this admin interface
# inlines: Displays related member badges inline in the admin form

# list_display: Controls which fields are displayed in the list view
# search_fields: Enables search by first name, last name, email, and username
# list_filter: Adds sidebar filters for membership status and member roles

# fieldsets: Organizes fields into logical sections in the admin form
#   - "Personal Info": Basic name, contact, and nickname fields
#   - "Membership": Membership status and internal club roles (DO, instructor, etc.)
#   - "Other Info": Address, rating, and notes fields
#   - "Permissions": Built-in Django auth flags and group permissions
#   - "Important Dates": Tracks login history

# add_fieldsets: Defines fields used during initial member creation
#   (uses "wide" layout for better visual spacing)


@admin.register(Member)
class MemberAdmin(AdminHelperMixin, ImportExportModelAdmin, VersionAdmin, UserAdmin):
    actions = ["export_members_csv", "mark_inactive"]

    @admin.action(description="Export selected members to CSV")
    def export_members_csv(self, request, queryset):
        # Define fields to export (exclude password, profile_photo, legacy name, badges, biography)
        fields = [
            "username",
            "first_name",
            "middle_initial",
            "last_name",
            "name_suffix",
            "nickname",
            "email",
            "phone",
            "mobile_phone",
            "emergency_contact",
            "membership_status",
            "date_joined",
            "private_glider_checkride_date",
            "instructor",
            "towpilot",
            "duty_officer",
            "assistant_duty_officer",
            "director",
            "member_manager",
            "rostermeister",
            "webmaster",
            "secretary",
            "treasurer",
            "address",
            "city",
            "state_code",
            "state_freeform",
            "zip_code",
            "country",
            "pilot_certificate_number",
            "SSA_member_number",
            "ssa_url",
            "glider_rating",
            "public_notes",
            "private_notes",
            "is_active",
            "is_staff",
            "is_superuser",
        ]
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=members_export.csv"
        writer = csv.writer(response)
        writer.writerow(fields)
        for member in queryset:
            row = [getattr(member, f, "") for f in fields]
            writer.writerow(row)
        return response

    readonly_fields = ("profile_photo_preview",)

    add_form = CustomMemberCreationForm
    form = CustomMemberChangeForm
    inlines = [MemberBadgeInline]

    list_display = (
        "last_name",
        "first_name",
        "email",
        "membership_status",
        "redact_contact",
    )
    search_fields = ("first_name", "last_name", "email", "username")
    list_filter = (
        "membership_status",
        "instructor",
        "towpilot",
        "director",
        "member_manager",
        "rostermeister",
        ActiveStatusFilter,
    )
    # Allow quick inline editing of membership status and redaction flag
    list_editable = ("membership_status", "redact_contact")
    # Allow filtering by redact flag in the admin sidebar
    list_filter = list_filter + ("redact_contact",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Personal Info",
            {
                "fields": (
                    "first_name",
                    "middle_initial",
                    "last_name",
                    "name_suffix",
                    "nickname",
                    "profile_photo",
                    "profile_photo_preview",
                    "email",
                    "phone",
                    "mobile_phone",
                    "emergency_contact",
                )
            },
        ),
        (
            "Membership",
            {
                "fields": (
                    "membership_status",
                    "date_joined",
                    "private_glider_checkride_date",
                    "instructor",
                    "towpilot",
                    "duty_officer",
                    "assistant_duty_officer",
                    "director",
                    "member_manager",
                    "rostermeister",
                    "webmaster",
                    "secretary",
                    "treasurer",
                )
            },
        ),
        (
            "Other Info",
            {
                "fields": (
                    "address",
                    "city",
                    "state_code",
                    "state_freeform",
                    "zip_code",
                    "country",
                    "pilot_certificate_number",
                    "SSA_member_number",
                    "ssa_url",
                    "glider_rating",
                    "private_notes",
                    "public_notes",
                    "redact_contact",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important Dates", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    @admin.display(description="Current Photo")
    def profile_photo_preview(self, obj):
        if obj.profile_photo:
            return format_html(
                '<img src="{}" style="max-height:200px; border:1px solid #ccc;" />',
                obj.profile_photo.url,
            )
        return ""

    def get_search_results(self, request, queryset, search_term):
        # Show all members (active and inactive) in admin
        return super().get_search_results(request, queryset, search_term)

    # Short helper shown at top of member admin pages; full guidance lives in docs/admin/members_delete.md
    admin_helper_message = (
        "Members: manage member profiles and roles. <br>See member deletion guidance."
    )
    admin_helper_doc_url = "https://github.com/pietbarber/Manage2Soar/tree/main/members/docs/admin/members_delete.md"

    @admin.action(description="Mark selected members inactive (safer than delete)")
    def mark_inactive(self, request, queryset):
        """Safe bulk action: mark selected members inactive instead of deleting.

        This preserves historical records (flights, reports, payments) while removing the member
        from active lists and preventing login.
        """
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Marked {updated} members as inactive.")


# --- MembershipApplication Admin ---


class ApplicationStatusFilter(SimpleListFilter):
    """Custom filter for membership application status with better grouping."""

    title = "application status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return (
            ("active", "Active (Pending/Under Review/Need Info)"),
            ("pending", "Pending"),
            ("under_review", "Under Review"),
            ("additional_info_needed", "Additional Info Needed"),
            ("waitlisted", "Waitlisted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("withdrawn", "Withdrawn"),
        )

    def queryset(self, request, queryset):
        if self.value() == "active":
            return queryset.filter(
                status__in=["pending", "under_review", "additional_info_needed"]
            )
        elif self.value():
            return queryset.filter(status=self.value())
        return queryset


@admin.register(MembershipApplication)
class MembershipApplicationAdmin(AdminHelperMixin, VersionAdmin, admin.ModelAdmin):
    """
    Django admin interface for membership applications.
    Provides comprehensive view and search for all applications including withdrawn ones.
    """

    list_display = [
        "full_name",
        "email",
        "status_badge",
        "glider_rating",
        "submitted_at",
        "reviewed_at",
        "reviewed_by",
        "days_since_submission",
    ]

    list_filter = [
        ApplicationStatusFilter,
        "glider_rating",
        "has_private_pilot",
        "has_commercial_pilot",
        "has_cfi",
        "country",
        "submitted_at",
        "reviewed_at",
        "reviewed_by",
    ]

    search_fields = [
        "first_name",
        "last_name",
        "email",
        "phone",
        "city",
        "state",
        "application_id",
    ]

    readonly_fields = [
        "application_id",
        "submitted_at",
        "full_name",
        "address_display",
        "aviation_summary",
        "days_since_submission",
    ]

    fieldsets = (
        (
            "Application Info",
            {
                "fields": (
                    "application_id",
                    "status",
                    "submitted_at",
                    "reviewed_at",
                    "reviewed_by",
                    "days_since_submission",
                )
            },
        ),
        (
            "Personal Information",
            {
                "fields": (
                    ("first_name", "middle_initial", "last_name", "name_suffix"),
                    "email",
                    ("phone", "mobile_phone"),
                    "address_display",
                    "country",
                )
            },
        ),
        (
            "Emergency Contact",
            {
                "fields": (
                    "emergency_contact_name",
                    "emergency_contact_relationship",
                    "emergency_contact_phone",
                )
            },
        ),
        (
            "Aviation Experience",
            {
                "fields": (
                    "aviation_summary",
                    "pilot_certificate_number",
                    "glider_rating",
                    ("has_private_pilot", "has_commercial_pilot", "has_cfi"),
                    (
                        "total_flight_hours",
                        "glider_flight_hours",
                        "recent_flight_hours",
                    ),
                    "ssa_member_number",
                )
            },
        ),
        (
            "History & Background",
            {
                "fields": (
                    "previous_club_memberships",
                    ("previous_member_at_this_club", "previous_membership_details"),
                    ("insurance_rejection_history", "insurance_rejection_details"),
                    ("club_rejection_history", "club_rejection_details"),
                    ("aviation_incidents", "aviation_incident_details"),
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Goals & Comments",
            {
                "fields": (
                    "soaring_goals",
                    "availability",
                    "additional_comments",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Management",
            {
                "fields": (
                    "admin_notes",
                    "waitlist_position",
                    "member_account",
                )
            },
        ),
    )

    date_hierarchy = "submitted_at"
    ordering = ["-submitted_at"]

    @admin.display(description="Name")
    def full_name(self, obj):
        """Display full name with suffix."""
        name_parts = [obj.first_name]
        if obj.middle_initial:
            name_parts.append(obj.middle_initial)
        name_parts.append(obj.last_name)
        if obj.name_suffix:
            name_parts.append(obj.name_suffix)
        return " ".join(name_parts)

    @admin.display(description="Status")
    def status_badge(self, obj):
        """Display status with color-coded badge."""
        colors = {
            "pending": "orange",
            "under_review": "blue",
            "additional_info_needed": "purple",
            "waitlisted": "gray",
            "approved": "green",
            "rejected": "red",
            "withdrawn": "darkgray",
        }
        color = colors.get(obj.status, "black")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Address")
    def address_display(self, obj):
        """Display formatted address."""
        parts = []
        if obj.address_line1:
            parts.append(obj.address_line1)
        if obj.address_line2:
            parts.append(obj.address_line2)
        city_state = []
        if obj.city:
            city_state.append(obj.city)
        if obj.state:
            city_state.append(obj.state)
        if city_state:
            parts.append(", ".join(city_state))
        if obj.zip_code:
            parts.append(obj.zip_code)
        if obj.country and obj.country != "USA":
            parts.append(obj.country)
        return "\n".join(parts)

    @admin.display(description="Aviation Experience")
    def aviation_summary(self, obj):
        """Display aviation experience summary."""
        summary = []
        if obj.glider_rating and obj.glider_rating != "none":
            summary.append(f"Glider: {obj.get_glider_rating_display()}")
        if obj.has_private_pilot:
            summary.append("Private Pilot")
        if obj.has_commercial_pilot:
            summary.append("Commercial Pilot")
        if obj.has_cfi:
            summary.append("CFI-G")
        if obj.total_flight_hours:
            summary.append(f"Total Hours: {obj.total_flight_hours}")
        if obj.glider_flight_hours:
            summary.append(f"Glider Hours: {obj.glider_flight_hours}")
        return "\n".join(summary) if summary else "No aviation experience"

    @admin.display(description="Submitted")
    def days_since_submission(self, obj):
        """Calculate days since application submission."""
        from django.utils import timezone

        days = (timezone.now() - obj.submitted_at).days
        return f"{days} days ago"

    def has_delete_permission(self, request, obj=None):
        """Restrict deletion - applications should be retained for records."""
        return False  # Never allow deletion of applications

    def get_actions(self, request):
        """Remove delete action since applications should never be deleted."""
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    # Admin helper guidance
    admin_helper_message = (
        "Membership Applications: View and manage all membership applications including withdrawn ones. "
        "Applications are never deleted to preserve club records. Use the web interface at "
        "/members/applications/ for application review workflow."
    )

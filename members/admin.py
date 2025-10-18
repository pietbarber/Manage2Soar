import csv

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

from .models import Badge, Biography, Member, MemberBadge

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

# This class defines the admin interface for the Badge model.
# It represents all possible types of soaring badges that can be awarded to
# members (e.g., SSA A, B, C, club-specific achievements, etc.).

# Admin users can use this interface to create, edit, and manage badge
# definitions.

# Fields typically include badge name, code, description, and any
# categorization fields.


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

admin.site.register(Badge, BadgeAdmin)


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
class MemberAdmin(ImportExportModelAdmin, VersionAdmin, UserAdmin):
    actions = ["export_members_csv"]

    def export_members_csv(self, request, queryset):
        # Define fields to export (exclude sensitive or generated fields such as
        # password, profile_photo, legacy name, badges, and biography)
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
            row = []
            for f in fields:
                row.append(getattr(member, f, ""))
            writer.writerow(row)
        return response

    export_members_csv.short_description = "Export selected members to CSV"
    readonly_fields = ("profile_photo_preview",)

    add_form = CustomMemberCreationForm
    form = CustomMemberChangeForm
    inlines = [MemberBadgeInline]

    list_display = ("last_name", "first_name", "email", "membership_status")
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

    def profile_photo_preview(self, obj):
        if obj.profile_photo:
            # Build a short HTML snippet for the image preview. Keep the
            # pieces on separate lines to stay under the line-length limit.
            img_html = (
                '<img src="{}" '
                'style="max-height:200px;" '
                'class="border" />'
            )
            return format_html(img_html, obj.profile_photo.url)
        return ""

    profile_photo_preview.short_description = "Current Photo"

    def get_search_results(self, request, queryset, search_term):
        # Show all members (active and inactive) in admin
        return super().get_search_results(request, queryset, search_term)

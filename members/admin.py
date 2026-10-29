import csv
import logging

from django import forms
from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models, router, transaction
from django.http import HttpResponse
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin
from reversion.admin import VersionAdmin
from tinymce.widgets import TinyMCE

from utils.admin_helpers import AdminHelperMixin

from .account_emails import send_account_setup_email
from .models import (
    Badge,
    Biography,
    EmergencyContact,
    KioskAccessLog,
    KioskToken,
    Member,
    MemberBadge,
    MemberTag,
    MemberTagAssignment,
    RoleMetadata,
    SafetyReport,
    VisitingPilotVisit,
)
from .models_applications import MembershipApplication
from .permission_sources import get_permission_sources
from .resources import (
    MEMBER_CSV_FIELDS,
    MemberResource,
    serialize_contact_visibility,
    serialize_emergency_contacts,
)
from .services.role_assignments import set_manual_role
from .utils.image_processing import generate_profile_thumbnails

logger = logging.getLogger(__name__)


def _instance_db(instance):
    """Return the database selected for an already-loaded model instance."""
    return instance._state.db or router.db_for_write(type(instance), instance=instance)


def _role_metadata_is_referenced(metadata):
    """Return whether a mailing list still uses this role's stable key."""
    if metadata is None:
        return False

    # Keep siteconfig out of module import time; it imports member-related code.
    from siteconfig.models import MailingList

    using = _instance_db(metadata)
    selector = f"role:{metadata.key}"
    return any(
        selector in (criteria or [])
        for criteria in MailingList.objects.using(using).values_list(
            "criteria", flat=True
        )
    )


class RoleMetadataInline(admin.StackedInline):
    """Optional role metadata editor for the Group admin.

    Metadata was added after Groups already existed, so the inline deliberately
    does not require a row.  This keeps legacy Groups manageable while making a
    metadata-backed custom role a one-page operation.
    """

    model = RoleMetadata
    extra = 1
    max_num = 1
    can_delete = True
    fields = (
        "key",
        "display_name",
        "description",
        ("is_builtin", "is_protected", "is_system_managed"),
        (
            "is_assignable",
            "mailing_list_eligible",
            "qualification_permission_bundle",
            "sort_order",
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        # A stable key and the provenance flags are immutable once metadata
        # exists.  obj is the parent Group supplied by InlineModelAdmin, so
        # check for the related row before making the fields read-only.
        return (
            ("key", "is_builtin", "is_protected", "is_system_managed")
            if obj
            and obj.pk
            and RoleMetadata.objects.using(_instance_db(obj))
            .filter(group_id=obj.pk)
            .exists()
            else ()
        )

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj is None:
            return True
        try:
            metadata = obj.role_metadata
        except RoleMetadata.DoesNotExist:
            return True
        return not metadata.is_protected and not _role_metadata_is_referenced(metadata)


class SuperuserOnlyGroupAdmin(DjangoGroupAdmin):
    """Emergency/bootstrap Group management until Platform Administrator exists."""

    inlines = (RoleMetadataInline,)

    def _is_authorized(self, request):
        return bool(
            request.user and request.user.is_active and request.user.is_superuser
        )

    def has_module_permission(self, request):
        return self._is_authorized(request)

    def has_view_permission(self, request, obj=None):
        return self._is_authorized(request)

    def has_add_permission(self, request):
        return self._is_authorized(request)

    def has_change_permission(self, request, obj=None):
        return self._is_authorized(request)

    def get_actions(self, request):
        # The bulk action calls queryset.delete() and cannot apply the
        # per-group protected/reference checks in has_delete_permission().
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None):
        if not self._is_authorized(request):
            return False
        if obj is None:
            return True
        try:
            metadata = obj.role_metadata
        except RoleMetadata.DoesNotExist:
            return True
        return not metadata.is_protected and not _role_metadata_is_referenced(metadata)


# auth.contrib.admin registers Group with its generic GroupAdmin.  Replace it
# here so the existing Group permissions UI remains intact while adding the
# deliberately narrower bootstrap access policy and metadata inline.
if admin.site.is_registered(Group):
    admin.site.unregister(Group)
admin.site.register(Group, SuperuserOnlyGroupAdmin)


class SuperuserOnlyTagAdmin(admin.ModelAdmin):
    """Bootstrap tag administration until the member-manager policy exists."""

    list_display = ("display_label", "key", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("key", "display_label", "description")
    ordering = ("sort_order", "display_label", "pk")
    readonly_fields = ()

    def _is_authorized(self, request):
        return bool(
            request.user and request.user.is_active and request.user.is_superuser
        )

    def has_module_permission(self, request):
        return self._is_authorized(request)

    def has_view_permission(self, request, obj=None):
        return self._is_authorized(request)

    def has_add_permission(self, request):
        return self._is_authorized(request)

    def has_change_permission(self, request, obj=None):
        return self._is_authorized(request)

    def has_delete_permission(self, request, obj=None):
        if not self._is_authorized(request):
            return False
        if obj is None:
            return True
        from siteconfig.models import MailingList

        using = _instance_db(obj)
        return not any(
            f"tag:{obj.key}" in (criteria or [])
            for criteria in MailingList.objects.using(using).values_list(
                "criteria", flat=True
            )
        )

    def get_actions(self, request):
        # queryset.delete() bypasses has_delete_permission; remove Django's
        # bulk action so every deletion gets the per-object guard.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_readonly_fields(self, request, obj=None):
        # The key is the stable reference used by future audience integrations.
        return ("key",) if obj else ()


class MemberTagAssignmentInline(admin.TabularInline):
    model = MemberTagAssignment
    extra = 1
    autocomplete_fields = ("member",)
    fields = ("member",)


@admin.register(MemberTag)
class MemberTagAdmin(SuperuserOnlyTagAdmin):
    inlines = (MemberTagAssignmentInline,)


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
    list_display = ["name", "order", "parent_badge", "leg_count"]
    list_filter = ["parent_badge"]
    search_fields = ["name", "description"]
    autocomplete_fields = ["parent_badge"]

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(_leg_count=models.Count("legs"))

    @admin.display(description="Legs")
    def leg_count(self, obj):
        """Display the number of legs for this badge."""
        return getattr(obj, "_leg_count", obj.legs.count())


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


class EmergencyContactInline(admin.TabularInline):
    model = EmergencyContact
    extra = 0


#########################
# CustomMemberChangeForm Class

# This form is used by the Django admin interface when editing an existing Member.
# It extends Django's built-in UserChangeForm and allows customization of field
# display, validation, and behavior specific to the Member model.


# This form is referenced by MemberAdmin via the 'form' attribute.
class CustomMemberChangeForm(UserChangeForm):
    CONTACT_VISIBILITY_CHOICES = (
        ("inherit", "Use club default"),
        ("share", "Share"),
        ("hide", "Hide"),
    )

    contact_visibility_email = forms.ChoiceField(
        label="Email visibility",
        choices=CONTACT_VISIBILITY_CHOICES,
        help_text="Controls visibility to regular members.",
    )
    contact_visibility_phone = forms.ChoiceField(
        label="Phone visibility",
        choices=CONTACT_VISIBILITY_CHOICES,
        help_text="Controls visibility to regular members.",
    )
    contact_visibility_address = forms.ChoiceField(
        label="Address visibility",
        choices=CONTACT_VISIBILITY_CHOICES,
        help_text="Controls visibility to regular members.",
    )

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        visibility = self.instance.contact_visibility or {}
        for field in ("email", "phone", "address"):
            self.fields[f"contact_visibility_{field}"].initial = (
                "hide"
                if self.instance.redact_contact
                else visibility.get(field, "inherit")
            )

    def save(self, commit=True):
        member = super().save(commit=False)
        member.contact_visibility = {
            field: self.cleaned_data[f"contact_visibility_{field}"]
            for field in ("email", "phone", "address")
            if self.cleaned_data[f"contact_visibility_{field}"] != "inherit"
        }
        member.redact_contact = False
        if commit:
            member.save()
        return member


#########################
# CustomMemberCreationForm Class

# This form is used by the Django admin interface when creating a new Member.
# It extends Django's built-in UserCreationForm and adds any custom validation
# or additional fields required by the Member model.

# This form is referenced by MemberAdmin via the 'add_form' attribute.


class CustomMemberCreationForm(UserCreationForm):
    send_account_setup_email = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Email the new member a secure link to choose their password.",
    )

    class Meta:
        model = Member
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].required = False
        self.fields["password2"].required = False

    def clean(self):
        cleaned_data = super().clean()
        send_email = cleaned_data.get("send_account_setup_email")
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if send_email and not cleaned_data.get("email"):
            self.add_error(
                "email", "An email address is required to send an account setup email."
            )

        if not send_email and not password1:
            self.add_error(
                "password1",
                "A password is required when not sending an account setup email.",
            )

        if not send_email and not password2:
            self.add_error(
                "password2",
                "Password confirmation is required when not sending an account setup email.",
            )

        return cleaned_data

    def save(self, commit=True):
        member = super().save(commit=False)
        if self.cleaned_data.get(
            "send_account_setup_email"
        ) and not self.cleaned_data.get("password1"):
            member.set_unusable_password()
        if commit:
            member.save()
        return member


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
    legacy_role_groups = {
        "Rostermeisters": "rostermeister",
        "Instructor Admins": "instructor",
        "Member Managers": "member_manager",
        "Webmasters": "webmaster",
        "Secretary": "secretary",
        "Treasurer": "treasurer",
    }
    privilege_fields = {
        "is_superuser",
        "is_staff",
        "groups",
        "user_permissions",
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
        "stats_monger",
        "safety_officer",
    }
    resource_classes = [MemberResource]
    actions = ["export_members_csv", "mark_inactive"]

    @admin.action(description="Export selected members to CSV")
    def export_members_csv(self, request, queryset):
        fields = list(MEMBER_CSV_FIELDS)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=members_export.csv"
        writer = csv.writer(response)
        writer.writerow(fields)
        for member in queryset.prefetch_related("emergency_contacts"):
            row = [
                (
                    serialize_emergency_contacts(member)
                    if field == "emergency_contacts"
                    else (
                        serialize_contact_visibility(member)
                        if field == "contact_visibility"
                        else getattr(member, field, "")
                    )
                )
                for field in fields
            ]
            writer.writerow(row)
        return response

    readonly_fields = (
        "profile_photo_preview",
        "redact_contact",
        "permission_source_summary",
    )

    add_form = CustomMemberCreationForm
    form = CustomMemberChangeForm
    inlines = [MemberBadgeInline, EmergencyContactInline]

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
    # Allow quick inline editing of membership status. `redact_contact` is
    # retired as a writable flag (see contact-privacy retirement): it is exposed
    # read-only so admins can still inspect it but cannot set the legacy
    # full-redaction override that members have no UI/endpoint to clear.
    list_editable = ("membership_status",)
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
                    "stats_monger",
                    "safety_officer",
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
                    "contact_visibility_email",
                    "contact_visibility_phone",
                    "contact_visibility_address",
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
                    "permission_source_summary",
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
                    "send_account_setup_email",
                ),
            },
        ),
    )

    def _limited_member_editor(self, request):
        """Member managers may edit members, but never account privileges."""
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_active
            and not user.is_superuser
            and user.has_perm("members.change_member")
        )

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if not self._limited_member_editor(request) or obj is None:
            return fieldsets
        return tuple(
            (
                title,
                {
                    **options,
                    "fields": tuple(
                        field
                        for field in options.get("fields", ())
                        if (field if isinstance(field, str) else field[0])
                        not in self.privilege_fields
                    ),
                },
            )
            for title, options in fieldsets
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

    def save_model(self, request, obj, form, change):
        """Generate thumbnails when a profile photo is uploaded via admin.

        Issue #479: When uploading photos via admin interface, thumbnails
        were not being generated. This ensures the same processing happens
        as when members upload their own photos.
        """
        # Save the pre-edit membership so save_related can distinguish a
        # direct admin grant from role synchronization.
        using = _instance_db(obj)
        obj._admin_groups_before = (
            set(obj.groups.db_manager(using).values_list("pk", flat=True))
            if obj.pk
            else set()
        )

        if "profile_photo" in form.changed_data and obj.profile_photo:
            try:
                thumbnails = generate_profile_thumbnails(obj.profile_photo)

                # Get base filename from original
                base_name = obj.profile_photo.name.split("/")[-1]

                # Save processed "original": resized/optimized (max 800x800) version replaces the upload
                obj.profile_photo.save(base_name, thumbnails["original"], save=False)

                # Save medium thumbnail (200x200) using same base filename as form upload
                obj.profile_photo_medium.save(
                    base_name,
                    thumbnails["medium"],
                    save=False,
                )

                # Save small thumbnail (64x64) using same base filename as form upload
                obj.profile_photo_small.save(
                    base_name,
                    thumbnails["small"],
                    save=False,
                )
            except (ValidationError, ValueError) as e:
                raise ValidationError(f"Photo processing failed: {e}")

        super().save_model(request, obj, form, change)

        # Use the database of the saved instance for all subsequent related
        # reads and writes.  This matters when the admin is used with a
        # database router (and also records the alias for save_related).
        using = _instance_db(obj)
        obj._admin_db = using

        if not change and form.cleaned_data.get("send_account_setup_email"):
            transaction.on_commit(lambda: self._send_account_setup_email_safely(obj))

    @admin.display(description="Effective permissions and all sources")
    def permission_source_summary(self, obj):
        if obj is None or not obj.pk:
            return "Save the member before inspecting permission sources."

        breakdown = get_permission_sources(obj)
        lines = []
        if breakdown["superuser_override"]:
            lines.append("SUPERUSER OVERRIDE: all permissions")
        for permission, detail in breakdown["permissions"].items():
            state = "effective" if detail["effective"] else "not effective"
            lines.append(f"{permission} [{state}]")
            for source in detail["sources"]:
                source_type = source["type"]
                if source_type == "direct":
                    label = "direct member permission"
                elif source_type == "group":
                    role = source.get("role_label") or source["group_name"]
                    provenance = source.get("source")
                    source_key = source.get("source_key")
                    reason = (
                        f"{provenance}:{source_key}"
                        if source_key is not None
                        else provenance
                    )
                    label = f"Group {role} ({reason})"
                    if source.get("actor_id"):
                        label += f", actor member #{source['actor_id']}"
                elif source_type == "qualification":
                    label = (
                        "qualification "
                        f"{source['qualification_code']} "
                        f"(record #{source['member_qualification_id']})"
                    )
                else:
                    label = source_type
                if not source.get("effective", False):
                    reason = source.get("ineffective_reason")
                    label += f" [not effective{f': {reason}' if reason else ''}]"
                lines.append(f"  - {label}")
        if not lines:
            lines.append("No configured permission sources.")
        lines.append("")
        lines.append(breakdown["cache_warning"])
        return format_html(
            "<pre style='white-space: pre-wrap'>{}</pre>", "\n".join(lines)
        )

    def save_related(self, request, form, formsets, change):
        member = form.instance
        using = getattr(member, "_admin_db", None) or _instance_db(member)
        before = getattr(member, "_admin_groups_before", set())
        cleaned_data = getattr(form, "cleaned_data", None)
        # ModelForm.save_m2m would replace Groups before provenance is written.
        # Save every other M2M/inline normally, but route the Groups selection
        # exclusively through the source-specific manual role service.
        selected_groups = None
        if cleaned_data is not None and "groups" in cleaned_data:
            selected_groups = cleaned_data.pop("groups")
        try:
            super().save_related(request, form, formsets, change)
        finally:
            if selected_groups is not None:
                cleaned_data["groups"] = selected_groups

        after = (
            {group.pk for group in selected_groups}
            if selected_groups is not None
            else set(member.groups.db_manager(using).values_list("pk", flat=True))
        )
        for group in Group.objects.using(using).filter(pk__in=after - before):
            # Legacy flag reconciliation owns this source while the flag is set.
            source_key = self.legacy_role_groups.get(group.name)
            if source_key and getattr(member, source_key, False):
                continue
            set_manual_role(member, group, enabled=True, actor=request.user)
        # If an administrator disables a legacy flag but deliberately leaves
        # its canonical Group selected, convert that selected membership to an
        # explicit manual source before the deferred legacy sync removes it.
        changed_fields = set(getattr(form, "changed_data", ()))
        for group in Group.objects.using(using).filter(pk__in=after):
            source_key = self.legacy_role_groups.get(group.name)
            if (
                source_key
                and source_key in changed_fields
                and not getattr(member, source_key, False)
            ):
                set_manual_role(member, group, enabled=True, actor=request.user)
        for group in Group.objects.using(using).filter(pk__in=before - after):
            set_manual_role(member, group, enabled=False)
            # The role-assignment backfill used this source for memberships
            # that had no recognizable legacy flag.  Removing a group in the
            # admin must revoke that source too, without touching any other
            # manual/status/legacy provenance.
            set_manual_role(member, group, enabled=False, source_key="migration")

    @staticmethod
    def _send_account_setup_email_safely(member):
        try:
            send_account_setup_email(member)
        except Exception:
            logger.exception(
                "Failed to send account setup email for admin-created member %s",
                member.pk,
            )


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


# =============================================================================
# Kiosk Token Admin (Issue #364)
# =============================================================================


@admin.register(KioskToken)
class KioskTokenAdmin(AdminHelperMixin, admin.ModelAdmin):
    """Admin interface for managing kiosk authentication tokens."""

    list_display = (
        "name",
        "user",
        "is_active",
        "is_device_bound_display",
        "last_used_at",
        "created_at",
    )
    list_filter = ("is_active", "landing_page")
    search_fields = ("name", "user__username", "user__first_name", "user__last_name")
    readonly_fields = (
        "token",
        "device_fingerprint",
        "created_at",
        "last_used_at",
        "last_used_ip",
        "magic_url_display",
    )
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "user", "is_active", "landing_page"),
            },
        ),
        (
            "Magic URL",
            {
                "fields": ("magic_url_display",),
                "description": "Bookmark this URL on the kiosk device for passwordless access.",
            },
        ),
        (
            "Device Binding",
            {
                "fields": ("device_fingerprint",),
                "description": "Device fingerprint is set automatically on first use.",
            },
        ),
        (
            "Usage Tracking",
            {
                "fields": ("last_used_at", "last_used_ip", "created_at"),
            },
        ),
        (
            "Notes",
            {
                "fields": ("notes",),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ["revoke_tokens", "regenerate_tokens", "unbind_devices"]

    @admin.display(description="Device Bound", boolean=True)
    def is_device_bound_display(self, obj):
        return obj.is_device_bound()

    @admin.display(description="Magic URL")
    def magic_url_display(self, obj):
        if obj.pk:
            from django.conf import settings

            # Get domain from settings or use placeholder
            # Note: We avoid django.contrib.sites to keep dependencies minimal
            domain = getattr(settings, "ALLOWED_HOSTS", ["localhost"])[0]
            if domain == "*":
                domain = "localhost:8001" if settings.DEBUG else "example.com"

            # Determine protocol for magic URL display
            # Prefer SECURE_SSL_REDIRECT setting over DEBUG flag to handle
            # staging/internal deployments correctly
            if getattr(settings, "SECURE_SSL_REDIRECT", False):
                protocol = "https"
            elif settings.DEBUG:
                protocol = "http"
            else:
                # Production without SSL redirect (e.g., behind load balancer)
                protocol = "https"

            url = obj.get_magic_url()
            full_url = f"{protocol}://{domain}{url}"
            return format_html(
                '<a href="{url}" target="_blank">{url}</a><br>'
                '<small class="text-muted">Copy this URL and bookmark it on the kiosk device.</small>',
                url=full_url,
            )
        return "Save to generate URL"

    @admin.action(description="Revoke selected tokens")
    def revoke_tokens(self, request, queryset):
        count = queryset.update(is_active=False)
        self.message_user(request, f"Revoked {count} kiosk token(s).")

    @admin.action(description="Regenerate tokens (new URLs)")
    def regenerate_tokens(self, request, queryset):
        count = 0
        for token in queryset:
            token.regenerate_token()
            count += 1
        self.message_user(
            request,
            f"Regenerated {count} token(s). Update bookmarks on affected devices.",
        )

    @admin.action(description="Unbind devices (allow re-binding)")
    def unbind_devices(self, request, queryset):
        count = queryset.update(device_fingerprint=None)
        self.message_user(
            request,
            f"Unbound {count} device(s). Tokens can now be bound to new devices.",
        )

    admin_helper_message = (
        "Kiosk Tokens: Manage passwordless authentication for dedicated kiosk devices. "
        "Each token is bound to a specific device fingerprint for security. "
        "Use 'Regenerate tokens' if a token URL is compromised, or 'Unbind devices' "
        "to allow a token to be used on a replacement device."
    )


@admin.register(KioskAccessLog)
class KioskAccessLogAdmin(admin.ModelAdmin):
    """Admin interface for viewing kiosk access audit logs."""

    list_display = (
        "timestamp",
        "kiosk_token",
        "status",
        "ip_address",
        "short_fingerprint",
    )
    list_filter = ("status", "timestamp", "kiosk_token")
    search_fields = ("token_value", "ip_address", "user_agent", "details")
    readonly_fields = (
        "kiosk_token",
        "token_value",
        "timestamp",
        "ip_address",
        "user_agent",
        "device_fingerprint",
        "status",
        "details",
    )
    date_hierarchy = "timestamp"
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        """Logs are created automatically, not manually."""
        return False

    def has_change_permission(self, request, obj=None):
        """Logs are read-only."""
        return False

    def has_delete_permission(self, request, obj=None):
        """
        Prevent deletion of kiosk access audit logs via admin.

        Audit logs are intended to be append-only to preserve the integrity of
        security investigations. If cleanup or retention management is needed,
        it should be implemented via a controlled archival/retention process
        (e.g., management command), not ad-hoc admin deletions.
        """
        return False

    @admin.display(description="Fingerprint")
    def short_fingerprint(self, obj):
        if obj.device_fingerprint:
            return obj.device_fingerprint[:12] + "..."
        return "-"


@admin.register(VisitingPilotVisit)
class VisitingPilotVisitAdmin(admin.ModelAdmin):
    """Admin interface for the visiting-pilot visit log used to enforce the yearly visit cap."""

    list_display = ("member", "visit_date", "logsheet", "created_at")
    list_filter = ("visit_date",)
    search_fields = ("member__first_name", "member__last_name", "member__email")
    date_hierarchy = "visit_date"
    ordering = ("-visit_date",)

    def has_add_permission(self, request):
        """Visits are logged automatically by the visiting-pilot signup flow."""
        return False


@admin.register(SafetyReport)
class SafetyReportAdmin(VersionAdmin, AdminHelperMixin, admin.ModelAdmin):
    """Admin interface for managing safety reports."""

    list_display = (
        "id",
        "get_reporter_display",
        "status",
        "observation_date",
        "location",
        "created_at",
        "reviewed_by",
    )
    list_filter = ("status", "is_anonymous", "created_at", "observation_date")
    search_fields = (
        "observation",
        "location",
        "reporter__first_name",
        "reporter__last_name",
        "reporter__username",
    )
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Report Details",
            {
                "fields": (
                    "reporter",
                    "is_anonymous",
                    "observation",
                    "observation_date",
                    "location",
                )
            },
        ),
        (
            "Status & Review",
            {
                "fields": (
                    "status",
                    "reviewed_by",
                    "reviewed_at",
                )
            },
        ),
        (
            "Officer Notes",
            {
                "fields": (
                    "officer_notes",
                    "actions_taken",
                ),
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
        "Safety Reports: Member-submitted safety observations. "
        "Anonymous reports have the reporter field hidden. "
        "Use officer_notes for internal review comments."
    )

    @admin.display(description="Reporter")
    def get_reporter_display(self, obj):
        return obj.get_reporter_display()

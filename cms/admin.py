from django.contrib import admin
from django.core.exceptions import ValidationError
from django.utils.html import format_html

from .models import (
    Document,
    HomePageContent,
    HomePageImage,
    Page,
    PageMemberPermission,
    PageRolePermission,
    SiteFeedback,
    VisitorContact,
)

# --- CMS Arbitrary Page and Document Admin ---


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 1
    fields = ("file", "title", "uploaded_at")
    readonly_fields = ("uploaded_at",)

    def save_new_instance(self, form, commit=True):
        obj = super().save_new_instance(form, commit=False)
        request = form.request if hasattr(form, "request") else None
        if request and not obj.uploaded_by:
            obj.uploaded_by = request.user
        if commit:
            obj.save()
        return obj

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.request = request
        return formset


class PageRolePermissionInline(admin.TabularInline):
    model = PageRolePermission
    extra = 3  # Show 3 empty forms to make it more visible
    fields = ("role_name",)
    verbose_name = "Role Permission"
    verbose_name_plural = "🔒 Role Permissions (For Private Pages Only)"


class PageMemberPermissionInline(admin.TabularInline):
    model = PageMemberPermission
    extra = 1
    fields = ("member",)
    autocomplete_fields = ["member"]
    verbose_name = "Member Permission"
    verbose_name_plural = "✏️ Content Editors (Grant EDIT access in Django admin)"


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    def get_queryset(self, request):
        """Prefetch role and member permissions to prevent N+1 queries in list view"""
        return (
            super()
            .get_queryset(request)
            .prefetch_related("role_permissions", "member_permissions")
        )

    list_display = (
        "title",
        "slug",
        "parent",
        "is_public",
        "role_summary",
        "member_summary",
        "updated_at",
    )
    search_fields = ("title", "slug")
    list_filter = ("is_public", "parent")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [
        PageRolePermissionInline,
        PageMemberPermissionInline,
        DocumentInline,
    ]

    # Custom fieldsets to organize the form
    fieldsets = (
        (None, {"fields": ("title", "slug", "parent", "content")}),
        (
            "Access Control",
            {
                "fields": ("is_public",),
                "description": (
                    "<strong>VIEW Permissions:</strong><br>"
                    "• Public pages: Accessible to everyone<br>"
                    "• Private pages: Accessible to active members only<br>"
                    "• Private with Role Permissions: Restricted to specific member roles<br><br>"
                    "<strong>EDIT Permissions:</strong><br>"
                    "Use the 'Content Editors' section below to grant specific members EDIT access in Django admin. "
                    "This works for both public and private pages - the page visibility remains unchanged, "
                    "but assigned members can edit the content."
                ),
            },
        ),
    )

    admin_helper_message = (
        "<b>CMS Pages:</b> Use this to create arbitrary pages and directories under /cms/. "
        "Set access control: Public (everyone), Private (active members), Role-based (specific positions), "
        "or assign specific members. Leave 'Parent' blank for top-level pages."
    )

    @admin.display(description="Role Restrictions")
    def role_summary(self, obj):
        """Display summary of role restrictions in list view"""
        if obj.is_public:
            return "Public"

        # Get roles once to avoid multiple queries
        roles = obj.get_required_roles()
        if not roles:
            return "Members Only"

        if len(roles) <= 2:
            return ", ".join(roles).title()
        else:
            return f"{len(roles)} roles required"

    @admin.display(description="Additional Editors")
    def member_summary(self, obj):
        """Display summary of members with explicit EDIT permissions.

        Shows members who can edit this page beyond the standard officers
        (directors, secretaries, webmasters).

        Works for both public and private pages - editors are shown regardless
        of page visibility.

        Note: This method relies on prefetch_related('member_permissions__member')
        in get_queryset() to prevent N+1 queries. If the prefetch is modified or
        removed, performance will degrade.
        """
        # Use prefetched data to avoid N+1 queries
        members = list(obj.member_permissions.all())
        if not members:
            return "-"

        if len(members) == 1:
            member = members[0].member
            return member.full_display_name
        else:
            return f"{len(members)} members"

    def has_module_permission(self, request):
        """Allow webmasters access to CMS admin."""
        return super().has_module_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_view_permission(self, request, obj=None):
        """Allow webmasters to view CMS pages."""
        return super().has_view_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_add_permission(self, request):
        """Allow webmasters to add CMS pages."""
        return super().has_add_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_change_permission(self, request, obj=None):
        """
        Allow webmasters, directors, secretaries, and members with explicit
        permissions to edit CMS pages.

        For object-level checks, delegate to Page.can_user_edit(), which already
        handles superuser access and role-based permissions.
        """
        # If editing a specific page, use its can_user_edit() method
        # (which handles superuser checks internally)
        if obj is not None:
            return obj.can_user_edit(request.user)

        # For list view, allow superusers and users with any edit rights
        if request.user.is_superuser:
            return True

        return request.user.is_authenticated and (
            getattr(request.user, "webmaster", False)
            or getattr(request.user, "director", False)
            or getattr(request.user, "secretary", False)
        )

    def has_delete_permission(self, request, obj=None):
        """Allow webmasters to delete CMS pages."""
        return super().has_delete_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def save_model(self, request, obj, form, change):
        """Add validation when saving"""
        try:
            # Call model's clean method to run custom validation
            obj.full_clean()
            super().save_model(request, obj, form, change)
        except ValidationError as e:
            from django.contrib import messages

            # Handle validation errors specifically
            if hasattr(e, "message_dict"):
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            elif hasattr(e, "messages"):
                for error in e.messages:
                    messages.error(request, error)
            else:
                messages.error(request, str(e))
            # Don't re-raise; save won't happen but user won't see double errors


@admin.register(PageRolePermission)
class PageRolePermissionAdmin(admin.ModelAdmin):
    list_display = ("page", "role_name", "page_is_public")
    list_filter = ("role_name", "page__is_public")
    search_fields = ("page__title", "page__slug")

    @admin.display(description="Page is Public", boolean=True)
    def page_is_public(self, obj):
        """Show if the associated page is public (which would be invalid)"""
        return obj.page.is_public

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("page")

    def has_module_permission(self, request):
        """Allow webmasters access to CMS role permissions."""
        return super().has_module_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_view_permission(self, request, obj=None):
        """Allow webmasters to view role permissions."""
        return super().has_view_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_add_permission(self, request):
        """Allow webmasters to add role permissions."""
        return super().has_add_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_change_permission(self, request, obj=None):
        """Allow webmasters to edit role permissions."""
        return super().has_change_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_delete_permission(self, request, obj=None):
        """Allow webmasters to delete role permissions."""
        return super().has_delete_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    list_display = ("title", "file", "page", "uploaded_by", "uploaded_at")
    search_fields = ("title", "file")
    list_filter = ("page",)
    exclude = ("uploaded_by",)

    admin_helper_message = (
        "<b>CMS Documents:</b> These are files (PDFs, images, etc.) attached to CMS Pages. "
        "To add a document to a page, use the inline form on the CMS Page itself."
    )

    def has_module_permission(self, request):
        """Allow webmasters access to CMS documents."""
        return super().has_module_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_view_permission(self, request, obj=None):
        """Allow webmasters to view documents."""
        return super().has_view_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_add_permission(self, request):
        """Allow webmasters to add documents."""
        return super().has_add_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_change_permission(self, request, obj=None):
        """Allow webmasters to edit documents."""
        return super().has_change_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_delete_permission(self, request, obj=None):
        """Allow webmasters to delete documents."""
        return super().has_delete_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def save_model(self, request, obj, form, change):
        if not obj.uploaded_by:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)


class HomePageImageInline(admin.TabularInline):
    model = HomePageImage
    extra = 1
    fields = ("image", "caption", "order")


@admin.register(HomePageContent)
class HomePageContentAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    list_display = ("title", "updated_at")
    search_fields = ("title",)
    inlines = [HomePageImageInline]

    admin_helper_message = (
        "<b>CMS Page Content:</b> Use this to edit the homepage or member homepage content. "
        "This is not used for arbitrary CMS pages under /cms/."
    )

    def has_module_permission(self, request):
        """Allow webmasters access to homepage content."""
        return super().has_module_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_view_permission(self, request, obj=None):
        """Allow webmasters to view homepage content."""
        return super().has_view_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_add_permission(self, request):
        """Allow webmasters to add homepage content."""
        return super().has_add_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_change_permission(self, request, obj=None):
        """Allow webmasters to edit homepage content."""
        return super().has_change_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_delete_permission(self, request, obj=None):
        """Allow webmasters to delete homepage content."""
        return super().has_delete_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )


@admin.register(HomePageImage)
class HomePageImageAdmin(admin.ModelAdmin):
    admin_helper_message = (
        "<b>CMS Page Images:</b> These images are attached to homepage or member homepage content. "
        "Use this to manage images for those special pages."
    )

    def has_module_permission(self, request):
        """Allow webmasters access to homepage images."""
        return super().has_module_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_view_permission(self, request, obj=None):
        """Allow webmasters to view homepage images."""
        return super().has_view_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_add_permission(self, request):
        """Allow webmasters to add homepage images."""
        return super().has_add_permission(request) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_change_permission(self, request, obj=None):
        """Allow webmasters to edit homepage images."""
        return super().has_change_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def has_delete_permission(self, request, obj=None):
        """Allow webmasters to delete homepage images."""
        return super().has_delete_permission(request, obj) or (
            request.user.is_authenticated and getattr(request.user, "webmaster", False)
        )

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    list_display = ("page", "caption", "order")
    list_filter = ("page",)


# Site Feedback Admin for Issue #117


@admin.register(SiteFeedback)
class SiteFeedbackAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    list_display = (
        "created_at",
        "user",
        "feedback_type",
        "subject",
        "status",
        "responded_by_name",
        "referring_page_link",
    )
    list_filter = ("feedback_type", "status", "created_at")
    search_fields = ("subject", "user__first_name", "user__last_name", "message")
    readonly_fields = (
        "user",
        "created_at",
        "updated_at",
        "responded_by",
        "referring_url",
    )

    # Group fields logically
    fieldsets = (
        (
            "Feedback Details",
            {
                "fields": (
                    "user",
                    "feedback_type",
                    "subject",
                    "message",
                    "referring_url",
                )
            },
        ),
        ("Status & Response", {"fields": ("status", "admin_response", "responded_by")}),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at", "resolved_at"),
                "classes": ("collapse",),
            },
        ),
    )

    # Allow filtering and bulk status updates
    actions = ["mark_resolved", "mark_in_progress", "mark_closed"]

    admin_helper_message = (
        "<b>Site Feedback:</b> Manage user feedback, bug reports, and feature requests. "
        "Users submit feedback through the site footer link."
    )

    @admin.display(description="Page")
    def referring_page_link(self, obj):
        """Display referring URL as a clickable link"""
        if obj.referring_url:
            return format_html(
                '<a href="{}" target="_blank" title="{}">📄 View Page</a>',
                obj.referring_url,
                obj.referring_url,
            )
        return "-"

    @admin.display(description="Responded By")
    def responded_by_name(self, obj):
        """Display who responded in the list view"""
        if obj.responded_by:
            return obj.responded_by.full_display_name
        return "-"

    @admin.action(description="Mark selected items as resolved")
    def mark_resolved(self, request, queryset):
        """Bulk action to mark feedback as resolved"""
        updated = queryset.update(status="resolved")
        self.message_user(request, f"{updated} feedback items marked as resolved.")

    @admin.action(description="Mark selected items as in progress")
    def mark_in_progress(self, request, queryset):
        """Bulk action to mark feedback as in progress"""
        updated = queryset.update(status="in_progress")
        self.message_user(request, f"{updated} feedback items marked as in progress.")

    @admin.action(description="Mark selected items as closed")
    def mark_closed(self, request, queryset):
        """Bulk action to mark feedback as closed"""
        updated = queryset.update(status="closed")
        self.message_user(request, f"{updated} feedback items marked as closed.")

    def save_model(self, request, obj, form, change):
        """Auto-set responded_by when webmaster adds a response"""
        if change and "admin_response" in form.changed_data and obj.admin_response:
            obj.responded_by = request.user
        super().save_model(request, obj, form, change)


# Visitor Contact Admin for Issue #70


@admin.register(VisitorContact)
class VisitorContactAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    list_display = (
        "submitted_at",
        "name",
        "email",
        "subject",
        "status",
        "handled_by_name",
        "ip_display",
    )
    list_filter = ("status", "submitted_at")
    search_fields = ("name", "email", "subject", "message")
    readonly_fields = ("submitted_at", "ip_address")

    # Group fields logically
    fieldsets = (
        (
            "Contact Details",
            {"fields": ("name", "email", "phone", "subject", "message")},
        ),
        ("Status & Management", {"fields": ("status", "handled_by", "admin_notes")}),
        (
            "Metadata",
            {"fields": ("submitted_at", "ip_address"), "classes": ("collapse",)},
        ),
    )

    # Allow filtering and bulk status updates
    actions = ["mark_read", "mark_responded", "mark_closed"]

    admin_helper_message = (
        "<b>Visitor Contacts:</b> Manage contact form submissions from website visitors. "
        "These are public inquiries from people interested in the club, replacing the "
        "spam-prone club public contact email address."
    )

    @admin.display(description="IP (Partial)")
    def ip_display(self, obj):
        """Display IP address in a truncated format for privacy"""
        if obj.ip_address:
            # Show only first 3 octets for privacy
            parts = obj.ip_address.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
            return obj.ip_address[:12] + "..."
        return "-"

    @admin.display(description="Handled By")
    def handled_by_name(self, obj):
        """Display who handled this contact in the list view"""
        if obj.handled_by:
            return obj.handled_by.full_display_name
        return "-"

    @admin.action(description="Mark selected items as read")
    def mark_read(self, request, queryset):
        """Bulk action to mark contacts as read"""
        updated = queryset.update(status="read")
        self.message_user(request, f"{updated} contact submissions marked as read.")

    @admin.action(description="Mark selected items as responded")
    def mark_responded(self, request, queryset):
        """Bulk action to mark contacts as responded"""
        updated = queryset.update(status="responded")
        self.message_user(
            request, f"{updated} contact submissions marked as responded."
        )

    @admin.action(description="Mark selected items as closed")
    def mark_closed(self, request, queryset):
        """Bulk action to mark contacts as closed"""
        updated = queryset.update(status="closed")
        self.message_user(request, f"{updated} contact submissions marked as closed.")

    def save_model(self, request, obj, form, change):
        """Auto-set handled_by when member manager takes action"""
        if change and (
            "status" in form.changed_data or "admin_notes" in form.changed_data
        ):
            # Always set to current user when making changes, regardless of existing value
            obj.handled_by = request.user
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        """Prevent manual creation of contacts - they should come from the form"""
        return False

    def get_readonly_fields(self, request, obj=None):
        """Make contact details readonly - this is submitted data"""
        readonly = list(self.readonly_fields)
        if obj:  # Editing existing object
            readonly.extend(
                ["name", "email", "phone", "subject", "message", "handled_by"]
            )
        return readonly


# Register your models here.

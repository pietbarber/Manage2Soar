from django.contrib import admin
from django.utils.html import format_html

from .models import Document, HomePageContent, HomePageImage, Page, SiteFeedback, VisitorContact

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


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    list_display = ("title", "slug", "parent", "is_public", "updated_at")
    search_fields = ("title", "slug")
    list_filter = ("is_public", "parent")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [DocumentInline]

    admin_helper_message = (
        "<b>CMS Pages:</b> Use this to create arbitrary pages and directories under /cms/. Attach documents below. "
        "Leave 'Parent' blank for top-level pages."
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


@admin.register(HomePageImage)
class HomePageImageAdmin(admin.ModelAdmin):
    admin_helper_message = (
        "<b>CMS Page Images:</b> These images are attached to homepage or member homepage content. "
        "Use this to manage images for those special pages."
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

    list_display = ('created_at', 'user', 'feedback_type',
                    'subject', 'status', 'responded_by_name', 'referring_page_link')
    list_filter = ('feedback_type', 'status', 'created_at')
    search_fields = ('subject', 'user__first_name', 'user__last_name', 'message')
    readonly_fields = ('user', 'created_at', 'updated_at',
                       'responded_by')

    # Group fields logically
    fieldsets = (
        ('Feedback Details', {
            'fields': ('user', 'feedback_type', 'subject', 'message', 'referring_url')
        }),
        ('Status & Response', {
            'fields': ('status', 'admin_response', 'responded_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'resolved_at'),
            'classes': ('collapse',)
        }),
    )

    # Allow filtering and bulk status updates
    actions = ['mark_resolved', 'mark_in_progress', 'mark_closed']

    admin_helper_message = (
        "<b>Site Feedback:</b> Manage user feedback, bug reports, and feature requests. "
        "Users submit feedback through the site footer link."
    )

    def referring_page_link(self, obj):
        """Display referring URL as a clickable link"""
        if obj.referring_url:
            return format_html(
                '<a href="{}" target="_blank" title="{}">📄 View Page</a>',
                obj.referring_url,
                obj.referring_url
            )
        return '-'
    referring_page_link.short_description = 'Page'

    def responded_by_name(self, obj):
        """Display who responded in the list view"""
        if obj.responded_by:
            return obj.responded_by.full_display_name
        return '-'
    responded_by_name.short_description = 'Responded By'

    def mark_resolved(self, request, queryset):
        """Bulk action to mark feedback as resolved"""
        updated = queryset.update(status='resolved')
        self.message_user(request, f'{updated} feedback items marked as resolved.')
    mark_resolved.short_description = "Mark selected items as resolved"

    def mark_in_progress(self, request, queryset):
        """Bulk action to mark feedback as in progress"""
        updated = queryset.update(status='in_progress')
        self.message_user(request, f'{updated} feedback items marked as in progress.')
    mark_in_progress.short_description = "Mark selected items as in progress"

    def mark_closed(self, request, queryset):
        """Bulk action to mark feedback as closed"""
        updated = queryset.update(status='closed')
        self.message_user(request, f'{updated} feedback items marked as closed.')
    mark_closed.short_description = "Mark selected items as closed"

    def save_model(self, request, obj, form, change):
        """Auto-set responded_by when webmaster adds a response"""
        if change and 'admin_response' in form.changed_data and obj.admin_response:
            obj.responded_by = request.user
        super().save_model(request, obj, form, change)


# Visitor Contact Admin for Issue #70

@admin.register(VisitorContact)
class VisitorContactAdmin(admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["admin_helper_message"] = self.admin_helper_message
        return super().changelist_view(request, extra_context=extra_context)

    list_display = ('submitted_at', 'name', 'email', 'subject',
                    'status', 'handled_by_name', 'ip_display')
    list_filter = ('status', 'submitted_at')
    search_fields = ('name', 'email', 'subject', 'message')
    readonly_fields = ('submitted_at', 'ip_address')

    # Group fields logically
    fieldsets = (
        ('Contact Details', {
            'fields': ('name', 'email', 'phone', 'subject', 'message')
        }),
        ('Status & Management', {
            'fields': ('status', 'handled_by', 'admin_notes')
        }),
        ('Metadata', {
            'fields': ('submitted_at', 'ip_address'),
            'classes': ('collapse',)
        }),
    )

    # Allow filtering and bulk status updates
    actions = ['mark_read', 'mark_responded', 'mark_closed']

    admin_helper_message = (
        "<b>Visitor Contacts:</b> Manage contact form submissions from website visitors. "
        "These are public inquiries from people interested in the club, replacing the "
        "spam-prone welcome@skylinesoaring.org email address."
    )

    def ip_display(self, obj):
        """Display IP address in a truncated format for privacy"""
        if obj.ip_address:
            # Show only first 3 octets for privacy
            parts = obj.ip_address.split('.')
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
            return obj.ip_address[:12] + "..."
        return '-'
    ip_display.short_description = 'IP (Partial)'

    def handled_by_name(self, obj):
        """Display who handled this contact in the list view"""
        if obj.handled_by:
            return obj.handled_by.full_display_name
        return '-'
    handled_by_name.short_description = 'Handled By'

    def mark_read(self, request, queryset):
        """Bulk action to mark contacts as read"""
        updated = queryset.update(status='read')
        self.message_user(request, f'{updated} contact submissions marked as read.')
    mark_read.short_description = "Mark selected items as read"

    def mark_responded(self, request, queryset):
        """Bulk action to mark contacts as responded"""
        updated = queryset.update(status='responded')
        self.message_user(
            request, f'{updated} contact submissions marked as responded.')
    mark_responded.short_description = "Mark selected items as responded"

    def mark_closed(self, request, queryset):
        """Bulk action to mark contacts as closed"""
        updated = queryset.update(status='closed')
        self.message_user(request, f'{updated} contact submissions marked as closed.')
    mark_closed.short_description = "Mark selected items as closed"

    def save_model(self, request, obj, form, change):
        """Auto-set handled_by when member manager takes action"""
        if change and ('status' in form.changed_data or 'admin_notes' in form.changed_data):
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
            readonly.extend(['name', 'email', 'phone',
                            'subject', 'message', 'handled_by'])
        return readonly


# Register your models here.

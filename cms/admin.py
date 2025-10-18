from django.contrib import admin

from .models import Document, HomePageContent, HomePageImage, Page

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


# Register your models here.

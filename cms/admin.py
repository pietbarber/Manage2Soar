from django.contrib import admin
from .models import HomePageContent, HomePageImage, Page, Document
# --- CMS Arbitrary Page and Document Admin ---


class DocumentInline(admin.TabularInline):
    model = Document
    extra = 1
    fields = ("file", "title", "uploaded_by", "uploaded_at")
    readonly_fields = ("uploaded_at",)


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "parent", "is_public", "updated_at")
    search_fields = ("title", "slug")
    list_filter = ("is_public", "parent")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [DocumentInline]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "file", "page", "uploaded_by", "uploaded_at")
    search_fields = ("title", "file")
    list_filter = ("page",)


class HomePageImageInline(admin.TabularInline):
    model = HomePageImage
    extra = 1
    fields = ("image", "caption", "order")


@admin.register(HomePageContent)
class HomePageContentAdmin(admin.ModelAdmin):
    list_display = ("title", "updated_at")
    search_fields = ("title",)
    inlines = [HomePageImageInline]


@admin.register(HomePageImage)
class HomePageImageAdmin(admin.ModelAdmin):
    list_display = ("page", "caption", "order")
    list_filter = ("page",)

# Register your models here.

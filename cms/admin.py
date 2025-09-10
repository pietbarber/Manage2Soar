from django.contrib import admin
from .models import HomePageContent, HomePageImage


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
    list_display = ("homepage_content", "caption", "order")
    list_filter = ("homepage_content",)

# Register your models here.

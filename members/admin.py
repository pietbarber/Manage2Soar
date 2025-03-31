from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Member
from tinymce.widgets import TinyMCE
from django.db import models
from .models import Badge
from django.utils.html import format_html
from django.contrib import admin
from .models import Member, Badge, MemberBadge



from django.contrib import admin
from .models import Biography

@admin.register(Biography)
class BiographyAdmin(admin.ModelAdmin):
    list_display = ("member", "updated_at")
    search_fields = ("member__first_name", "member__last_name", "member__email")
    ordering = ("-updated_at",)

from .models import Badge, MemberBadge

@admin.register(MemberBadge)
class MemberBadgeAdmin(admin.ModelAdmin):
    list_display = ("member", "badge", "date_awarded")
    list_filter = ("badge",)
    search_fields = ("member__first_name", "member__last_name", "badge__name")

class BadgeAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.TextField: {'widget': TinyMCE(attrs={'cols': 80, 'rows': 10})},
    }
    search_fields = ['name', 'description']  

admin.site.register(Badge, BadgeAdmin)
class MemberBadgeInline(admin.TabularInline):
    model = MemberBadge
    extra = 1  # Show one empty row to add a badge
    autocomplete_fields = ["badge"]  # Optional: if you have lots of badges


from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import Member, MemberBadge

class CustomMemberCreationForm(UserCreationForm):
    class Meta:
        model = Member
        fields = ("username", "email", "first_name", "last_name")

class CustomMemberChangeForm(UserChangeForm):
    class Meta:
        model = Member
        fields = ("username", "email", "first_name", "last_name", "membership_status", "instructor", "towpilot")
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib import admin
from .models import Member, MemberBadge

class CustomMemberCreationForm(UserCreationForm):
    class Meta:
        model = Member
        fields = ("username", "email", "first_name", "last_name")

class CustomMemberChangeForm(UserChangeForm):
    class Meta:
        model = Member
        fields = ("username", "email", "first_name", "last_name", "membership_status", "instructor", "towpilot")

class MemberBadgeInline(admin.TabularInline):
    model = MemberBadge
    extra = 0

@admin.register(Member)
class MemberAdmin(UserAdmin):
    add_form = CustomMemberCreationForm
    form = CustomMemberChangeForm
    model = Member
    inlines = [MemberBadgeInline]

    list_display = ("last_name", "first_name", "email", "membership_status")
    search_fields = ("first_name", "last_name", "email")
    list_filter = ("membership_status", "instructor", "towpilot")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Membership", {"fields": ("membership_status", "instructor", "towpilot")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "first_name", "last_name", "password1", "password2"),
        }),
    )

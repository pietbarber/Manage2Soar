from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Member
from tinymce.widgets import TinyMCE
from django.db import models
from .models import Badge

class BadgeAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.TextField: {'widget': TinyMCE(attrs={'cols': 80, 'rows': 10})},
    }

admin.site.register(Badge, BadgeAdmin)

@admin.register(Member)
class MemberAdmin(UserAdmin):
    model = Member
    list_display = ("username", "email", "is_staff", "is_active")


from .models import Glider

@admin.register(Glider)
class GliderAdmin(admin.ModelAdmin):
    list_display = ('n_number', 'make', 'model', 'number_of_seats', 'rental_rate')
    search_fields = ('n_number', 'make', 'model', 'competition_number')

from .models import Badge, MemberBadge

admin.site.register(MemberBadge)

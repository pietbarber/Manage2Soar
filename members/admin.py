from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Member

class MemberAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'glider_rating')
    list_filter = ('glider_rating', 'secretary', 'treasurer', 'webmaster')

admin.site.register(Member, MemberAdmin)

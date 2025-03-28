from django.urls import path
from . import views

app_name = "instructors"

urlpatterns = [
    path("", views.index, name="index"),
]

from django.conf.urls import handler403
handler403 = "django.views.defaults.permission_denied"

from django.urls import path
from . import views

app_name = "logsheet"

urlpatterns = [
    path("", views.index, name="index"),
    path("create/", views.create_logsheet, name="create"), 
    path("correct/", views.index, name="correct"),
    path("manage/<int:pk>/", views.manage_logsheet, name="manage"),

] 

from django.conf.urls import handler403
handler403 = "django.views.defaults.permission_denied"

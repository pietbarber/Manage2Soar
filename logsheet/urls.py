from django.urls import path
from . import views

app_name = "logsheet"

urlpatterns = [
    path("", views.list_logsheets, name="index"),
    path("create/", views.create_logsheet, name="create"), 
    path("correct/", views.index, name="correct"),
    path("manage/<int:pk>/", views.manage_logsheet, name="manage"),
    path("manage/<int:logsheet_pk>/edit-flight/<int:flight_pk>/", views.edit_flight, name="edit_flight"),
    path("manage/<int:logsheet_pk>/add-flight/", views.add_flight, name="add_flight"),


] 

from django.conf.urls import handler403
handler403 = "django.views.defaults.permission_denied"

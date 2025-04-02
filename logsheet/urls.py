from django.urls import path
from . import views

app_name = "logsheet"

urlpatterns = [
    path("", views.list_logsheets, name="index"),
    path("create/", views.create_logsheet, name="create"), 
    path("manage/<int:pk>/", views.manage_logsheet, name="manage"),
    path("manage/<int:logsheet_pk>/edit-flight/<int:flight_pk>/", views.edit_flight, name="edit_flight"),
    path("manage/<int:logsheet_pk>/add-flight/", views.add_flight, name="add_flight"),
    path("manage/<int:logsheet_pk>/delete-flight/<int:flight_pk>/",views.delete_flight,name="delete_flight"),
    path("manage/<int:pk>/finances/", views.manage_logsheet_finances, name="manage_logsheet_finances"),
    path("manage/<int:pk>/closeout/", views.edit_logsheet_closeout, name="edit_logsheet_closeout"),
    path("manage/<int:pk>/view-closeout/", views.view_logsheet_closeout, name="view_logsheet_closeout"),

] 

from django.conf.urls import handler403
handler403 = "django.views.defaults.permission_denied"



from django.urls import path
from . import views

app_name = "logsheet"

urlpatterns = [
    path("", views.list_logsheets, name="index"),
    path("create/", views.create_logsheet, name="create"),
    path("flight/<int:pk>/view/", views.view_flight, name="flight_view"),
    path("manage/<int:pk>/", views.manage_logsheet, name="manage"),
    path("manage/<int:logsheet_pk>/edit-flight/<int:flight_pk>/",
         views.edit_flight, name="edit_flight"),
    path("manage/<int:logsheet_pk>/add-flight/",
         views.add_flight, name="add_flight"),
    path("manage/<int:logsheet_pk>/delete-flight/<int:flight_pk>/",
         views.delete_flight, name="delete_flight"),
    path("manage/<int:pk>/finances/", views.manage_logsheet_finances,
         name="manage_logsheet_finances"),
    path("manage/<int:pk>/closeout/", views.edit_logsheet_closeout,
         name="edit_logsheet_closeout"),
    path("manage/<int:pk>/view-closeout/",
         views.view_logsheet_closeout, name="view_logsheet_closeout"),
    path("logsheet/<int:logsheet_id>/add-issue/",
         views.add_maintenance_issue, name="add_maintenance_issue"),
    path("equipment/", views.equipment_list, name="equipment_list"),
    path("maintenance/", views.maintenance_issues, name="maintenance_issues"),
    path("maintenance/resolve-modal/<int:issue_id>/",
         views.maintenance_resolve_modal, name="maintenance_resolve_modal"),
    path("maintenance/resolve/<int:issue_id>/",
         views.maintenance_mark_resolved, name="maintenance_mark_resolved"),
    path("maintenance-deadlines/", views.maintenance_deadlines,
         name="maintenance_deadlines"),
    path("equipment/glider/<int:pk>/logbook/",
         views.glider_logbook, name="glider_logbook"),
    path("equipment/towplane/<int:pk>/logbook/",
         views.towplane_logbook, name="towplane_logbook"),

    # AJAX API endpoint for duty assignment lookup
    path("api/duty-assignment/", views.api_duty_assignment,
         name="api_duty_assignment"),
    path("delete/<int:pk>/", views.delete_logsheet, name="delete"),


    # AJAX endpoint for instant launch/landing
    path("flight/<int:flight_id>/launch_now/",
         views.launch_flight_now, name="launch_flight_now"),
    path("flight/<int:flight_id>/landing_now/",
         views.land_flight_now, name="land_flight_now"),

    # AJAX endpoint for updating split fields
    path("flight/<int:flight_id>/update_split/",
         views.update_flight_split, name="update_flight_split"),
    # AJAX endpoint for updating split fields
    path("flight/<int:flight_id>/update_split/",
         views.update_flight_split, name="update_flight_split"),

]

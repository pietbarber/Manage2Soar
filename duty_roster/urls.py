from django.urls import path
from . import views

app_name = "duty_roster"

urlpatterns = [
    path("", views.roster_home, name="roster_home"),
    path("blackout/", views.blackout_manage, name="blackout_manage"),
    path("calendar/", views.duty_calendar_view, name="duty_calendar"),
    path("calendar/<int:year>/<int:month>/", views.duty_calendar_view, name="duty_calendar_month"),
    path("calendar/day/<int:year>/<int:month>/<int:day>/", views.calendar_day_detail, name="calendar_day_detail"),
    path("calendar/day/<int:year>/<int:month>/<int:day>/intent/", views.ops_intent_toggle, name="ops_intent_toggle"),
    path("calendar/day/<int:year>/<int:month>/<int:day>/intent/form/", views.ops_intent_form, name="ops_intent_form"),
    path("calendar/day/<int:year>/<int:month>/<int:day>/edit/", views.assignment_edit_form, name="assignment_edit_form"),
    path("calendar/day/<int:year>/<int:month>/<int:day>/save/", views.assignment_save_form, name="assignment_save_form"),

]

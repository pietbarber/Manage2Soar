from django.urls import path

from . import views

app_name = "duty_roster"

urlpatterns = [
    path("", views.roster_home, name="roster_home"),
    path("blackout/", views.blackout_manage, name="blackout_manage"),
    path("calendar/", views.duty_calendar_view, name="duty_calendar"),
    path(
        "calendar/<int:year>/<int:month>/",
        views.duty_calendar_view,
        name="duty_calendar_month",
    ),
    path(
        "calendar/day/<int:year>/<int:month>/<int:day>/",
        views.calendar_day_detail,
        name="calendar_day_detail",
    ),
    path(
        "calendar/day/<int:year>/<int:month>/<int:day>/intent/",
        views.ops_intent_toggle,
        name="ops_intent_toggle",
    ),
    path(
        "calendar/day/<int:year>/<int:month>/<int:day>/intent/form/",
        views.ops_intent_form,
        name="ops_intent_form",
    ),
    path(
        "calendar/day/<int:year>/<int:month>/<int:day>/edit/",
        views.assignment_edit_form,
        name="assignment_edit_form",
    ),
    path(
        "calendar/day/<int:year>/<int:month>/<int:day>/save/",
        views.assignment_save_form,
        name="assignment_save_form",
    ),
    path(
        "calendar/tow-signup/<int:year>/<int:month>/<int:day>/",
        views.calendar_tow_signup,
        name="calendar_tow_signup",
    ),
    path(
        "calendar/dutyofficer-signup/<int:year>/<int:month>/<int:day>/",
        views.calendar_dutyofficer_signup,
        name="calendar_dutyofficer_signup",
    ),
    path(
        "calendar/instructor-signup/<int:year>/<int:month>/<int:day>/",
        views.calendar_instructor_signup,
        name="calendar_instructor_signup",
    ),
    path(
        "calendar/ado-signup/<int:year>/<int:month>/<int:day>/",
        views.calendar_ado_signup,
        name="calendar_ado_signup",
    ),
    path(
        "calendar/ad-hoc/<int:year>/<int:month>/<int:day>/",
        views.calendar_ad_hoc_start,
        name="calendar_ad_hoc_start",
    ),
    path(
        "calendar/ad-hoc/confirm/<int:year>/<int:month>/<int:day>/",
        views.calendar_ad_hoc_confirm,
        name="calendar_ad_hoc_confirm",
    ),
    path(
        "calendar/ad-hoc/cancel/<int:year>/<int:month>/<int:day>/",
        views.calendar_cancel_ops_modal,
        name="calendar_cancel_ops_modal",
    ),
    path(
        "calendar/ad-hoc/cancel/confirm/<int:year>/<int:month>/<int:day>/",
        views.calendar_cancel_ops_day,
        name="calendar_cancel_ops_day",
    ),
    path("propose-roster/", views.propose_roster, name="propose_roster"),
]

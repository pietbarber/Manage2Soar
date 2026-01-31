from django.conf import settings
from django.conf.urls import handler403
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import include, path

from . import views, views_applications, views_kiosk, views_safety_reports
from .views import tinymce_image_upload

app_name = "members"

urlpatterns = [
    path("", views.member_list, name="member_list"),
    path("badges/", views.badge_board, name="badge_board"),
    path("<int:member_id>/biography/", views.biography_view, name="biography_view"),
    path("tinymce/", include("tinymce.urls")),
    path("<int:member_id>/view/", views.member_view, name="member_view"),
    path("set-password/", views.set_password, name="set_password"),
    path("tinymce-upload/", tinymce_image_upload, name="tinymce_image_upload"),
    path(
        "training-progress/",
        lambda req: redirect("instructors:member_training_grid", req.user.pk),
        name="training_progress",
    ),
    path(
        "<int:member_id>/toggle-redaction/",
        views.toggle_redaction,
        name="toggle_redaction",
    ),
    # Kiosk authentication URLs (Issue #364)
    path(
        "kiosk/<str:token>/",
        views_kiosk.kiosk_login,
        name="kiosk_login",
    ),
    path(
        "kiosk/<str:token>/bind/",
        views_kiosk.kiosk_bind_device,
        name="kiosk_bind_device",
    ),
    path(
        "kiosk/<str:token>/verify/",
        views_kiosk.kiosk_verify_device,
        name="kiosk_verify_device",
    ),
    # Visiting pilot URLs
    path(
        "visiting-pilot/signup/<str:token>/",
        views.visiting_pilot_signup,
        name="visiting_pilot_signup",
    ),
    path(
        "visiting-pilot/qr/",
        views.visiting_pilot_qr_code,
        name="visiting_pilot_qr_code",
    ),
    path(
        "visiting-pilot/qr-display/",
        views.visiting_pilot_qr_display,
        name="visiting_pilot_qr_display",
    ),
    # Membership Application URLs
    path(
        "apply/",
        views_applications.membership_application,
        name="membership_application",
    ),
    path(
        "applications/",
        views_applications.membership_applications_list,
        name="membership_applications_list",
    ),
    path(
        "applications/<uuid:application_id>/",
        views_applications.membership_application_detail,
        name="membership_application_detail",
    ),
    path(
        "applications/waitlist/",
        views_applications.membership_waitlist,
        name="membership_waitlist",
    ),
    path(
        "application-status/<uuid:application_id>/",
        views_applications.membership_application_status,
        name="membership_application_status",
    ),
    # Safety Reports
    path(
        "safety-report/submit/",
        views.safety_report_submit,
        name="safety_report_submit",
    ),
    # Safety Officer Interface (Issue #585)
    path(
        "safety-reports/",
        views_safety_reports.safety_report_list,
        name="safety_report_list",
    ),
    path(
        "safety-reports/<int:report_id>/",
        views_safety_reports.safety_report_detail,
        name="safety_report_detail",
    ),
]


handler403 = "django.views.defaults.permission_denied"


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

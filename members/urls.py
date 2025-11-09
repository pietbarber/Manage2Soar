from django.conf import settings
from django.conf.urls import handler403
from django.conf.urls.static import static
from django.shortcuts import redirect
from django.urls import include, path

from . import views
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
]


handler403 = "django.views.defaults.permission_denied"


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.urls import path

from . import views

app_name = "siteconfig"

urlpatterns = [
    # Visiting pilot URLs moved to members app
    path("webcam/", views.webcam_page, name="webcam"),
    path("webcam/snapshot/", views.webcam_snapshot, name="webcam_snapshot"),
]

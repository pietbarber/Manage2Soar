from django.urls import path, re_path

from . import views

app_name = 'cms'

urlpatterns = [
    path("", views.homepage, name="home"),
    # Site feedback URLs (Issue #117)
    path("feedback/", views.submit_feedback, name="feedback"),
    path("feedback/success/", views.feedback_success, name="feedback_success"),
    # /cms/<slug>/ or /cms/<parent>/<slug>/ (supports up to 3 levels for now)
    re_path(r"^(?P<slug1>[-\w]+)/$", views.cms_page, name="cms_page"),
    re_path(
        r"^(?P<slug1>[-\w]+)/(?P<slug2>[-\w]+)/$",
        views.cms_page,
        name="cms_page_nested",
    ),
    re_path(
        r"^(?P<slug1>[-\w]+)/(?P<slug2>[-\w]+)/(?P<slug3>[-\w]+)/$",
        views.cms_page,
        name="cms_page_nested2",
    ),
]

from django.urls import path

from . import views
from .views import CreateWrittenTestView

app_name = "instructors"

urlpatterns = [
    path("", views.progress_dashboard, name="instructors-dashboard"),
    path("syllabus/", views.syllabus_overview_grouped, name="syllabus_overview"),
    path("syllabus/<str:code>/", views.syllabus_detail, name="syllabus_detail"),
    path(
        "syllabus/edit-document/<slug:slug>/",
        views.edit_syllabus_document,
        name="edit_syllabus_document",
    ),
    path(
        "report/select-date/<int:student_id>/",
        views.select_instruction_date,
        name="select_instruction_date",
    ),
    path(
        "report/<int:student_id>/<slug:report_date>/",
        views.fill_instruction_report,
        name="fill_instruction_report",
    ),
    path(
        "training-grid/<int:member_id>/",
        views.member_training_grid,
        name="member_training_grid",
    ),
    path(
        "instruction-record/<int:member_id>/",
        views.member_instruction_record,
        name="member_instruction_record",
    ),
    path(
        "log-ground-instruction/",
        views.log_ground_instruction,
        name="log_ground_instruction",
    ),
    path(
        "assign-qualification/<int:member_id>/",
        views.assign_qualification,
        name="assign_qualification",
    ),
    path("logbook/", views.member_logbook, name="member_logbook"),
    path("logbook/loading/", views.logbook_loading, name="logbook_loading"),
    path(
        "logbook/export/csv/",
        views.export_member_logbook_csv,
        name="member_logbook_export_csv",
    ),
    path(
        "students/<int:member_id>/needed-for-solo/",
        views.needed_for_solo,
        name="needed_for_solo",
    ),
    path(
        "students/<int:member_id>/needed-for-checkride/",
        views.needed_for_checkride,
        name="needed_for_checkride",
    ),
    path(
        "reports/<int:report_id>/detail/",
        views.instruction_report_detail,
        name="instruction_report_detail",
    ),
    path("tests/create/", CreateWrittenTestView.as_view(), name="create-written-test"),
]

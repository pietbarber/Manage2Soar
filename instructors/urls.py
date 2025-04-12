from django.urls import path
from . import views

app_name = "instructors"

urlpatterns = [
    path("", views.instructors_home, name="index"),
    path("syllabus/", views.syllabus_overview_grouped, name="syllabus_overview"),
    path("syllabus/<str:code>/", views.syllabus_detail, name="syllabus_detail"),
    path("report/select-date/<int:student_id>/", views.select_instruction_date, name="select_instruction_date"),
    path("report/<int:student_id>/<slug:report_date>/", views.fill_instruction_report, name="fill_instruction_report"),
    path("training-grid/<int:member_id>/", views.member_training_grid, name="member_training_grid"),

]


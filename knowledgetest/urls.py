from django.urls import path

from instructors.views import WrittenTestReviewView

from .views import (
    CreateWrittenTestView,
    PendingTestsView,
    WrittenTestResultView,
    WrittenTestStartView,
    WrittenTestSubmitView,
    WrittenTestAttemptDeleteView,
    MemberWrittenTestHistoryView,
    InstructorRecentTestsView,
)

app_name = "knowledgetest"

urlpatterns = [
    path("create/", CreateWrittenTestView.as_view(), name="create"),
    path("tests/<int:pk>/start/", WrittenTestStartView.as_view(), name="quiz-start"),
    path("tests/<int:pk>/submit/", WrittenTestSubmitView.as_view(), name="quiz-submit"),
    path("attempt/<int:pk>/", WrittenTestResultView.as_view(), name="quiz-result"),
    path("attempt/<int:pk>/delete/", WrittenTestAttemptDeleteView.as_view(),
         name="quiz-attempt-delete"),
    path("pending/", PendingTestsView.as_view(), name="quiz-pending"),
    path("history/", MemberWrittenTestHistoryView.as_view(), name="member-test-history"),
    path("instructor/recent/", InstructorRecentTestsView.as_view(),
         name="instructor-recent-tests"),
    path(
        "tests/<int:pk>/review/<int:student_pk>/",
        WrittenTestReviewView.as_view(),
        name="quiz-review",
    ),
]

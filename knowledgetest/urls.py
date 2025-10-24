from django.urls import path

from instructors.views import WrittenTestReviewView

from .views import (
    PendingTestsView,
    WrittenTestResultView,
    WrittenTestStartView,
    WrittenTestSubmitView,
    WrittenTestAttemptDeleteView,
)

app_name = "knowledgetest"

urlpatterns = [
    path("tests/<int:pk>/start/", WrittenTestStartView.as_view(), name="quiz-start"),
    path("tests/<int:pk>/submit/", WrittenTestSubmitView.as_view(), name="quiz-submit"),
    path("attempt/<int:pk>/", WrittenTestResultView.as_view(), name="quiz-result"),
    path("attempt/<int:pk>/delete/", WrittenTestAttemptDeleteView.as_view(),
         name="quiz-attempt-delete"),
    path("pending/", PendingTestsView.as_view(), name="quiz-pending"),
    path(
        "tests/<int:pk>/review/<int:student_pk>/",
        WrittenTestReviewView.as_view(),
        name="quiz-review",
    ),
]

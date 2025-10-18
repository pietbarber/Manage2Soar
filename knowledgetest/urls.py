from django.urls import path

from instructors.views import WrittenTestReviewView

from .views import (
    PendingTestsView,
    WrittenTestResultView,
    WrittenTestStartView,
    WrittenTestSubmitView,
)

app_name = "knowledgetest"

urlpatterns = [
    path("tests/<int:pk>/start/", WrittenTestStartView.as_view(), name="quiz-start"),
    path("tests/<int:pk>/submit/", WrittenTestSubmitView.as_view(), name="quiz-submit"),
    path("attempt/<int:pk>/", WrittenTestResultView.as_view(), name="quiz-result"),
    path("pending/", PendingTestsView.as_view(), name="quiz-pending"),
    path(
        "tests/<int:pk>/review/<int:student_pk>/",
        WrittenTestReviewView.as_view(),
        name="quiz-review",
    ),
]

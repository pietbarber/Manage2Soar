from django.urls import path
from .views import (
    WrittenTestStartView,
    WrittenTestSubmitView,
    WrittenTestResultView,
    PendingTestsView
)

app_name = 'knowledgetest'

urlpatterns = [
    path('tests/<int:pk>/start/', WrittenTestStartView.as_view(), name='quiz-start'),
    path( 'tests/<int:pk>/submit/', WrittenTestSubmitView.as_view(), name='quiz-submit'),
    path( 'attempt/<int:pk>/', WrittenTestResultView.as_view(), name='quiz-result'),
    path('pending/', PendingTestsView.as_view(), name='quiz-pending')

]

from django.urls import path
from .views import DueFlashcardsView, UpdatePerformanceView

urlpatterns = [
    path(
        'api/flashcards/due/',
        DueFlashcardsView.as_view(),
        name='due-flashcards',
    ),
    path(
        'api/flashcards/<int:pk>/update/',
        UpdatePerformanceView.as_view(),
        name='update-performance',
    ),
]

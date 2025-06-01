from django.urls import path
from .views import (
    ProfileView,
    UploadDeckView,
    HomeView,
    deck_session_view,
    update_card_view,
    DueDecksHTMLView,
    login_view,
    register_view,
    logout_view
)

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('decks/<int:deck_id>/session/', deck_session_view, name='deck_session'),
    path('cards/<int:pk>/update/', update_card_view, name='update_card'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('upload/', UploadDeckView.as_view(), name='upload'),
    path('due_decks', DueDecksHTMLView.as_view(), name='due-decks')
]

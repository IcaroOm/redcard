import os
import logging 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.urls import reverse_lazy
from rest_framework.views import APIView
from rest_framework import status
from flashcards.models import Deck, Card
from .forms import LoginForm, RegisterForm
from flashcards.services import AnkiImporterService, AnkiImportError

logger = logging.getLogger(__name__)

FLASHCARD_SESSION_DECK_ID = 'flashcard_session_deck_id'
FLASHCARD_SESSION_CARD_IDS = 'flashcard_session_card_ids'
FLASHCARD_SESSION_CURRENT_CARD_INDEX = 'flashcard_session_current_card_index'


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = LoginForm()
    return render(request, 'auth/login.html', {'form': form})

def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'auth/register.html', {'form': form})

@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect('login') 

@method_decorator(login_required, name='dispatch')
class HomeView(APIView):
    def get(self, request):
        due_decks_context = []
        decks = Deck.objects.filter(user=request.user)
        for deck in decks:
            due_cards_for_deck = deck.get_due_cards() 
            if due_cards_for_deck.exists():
                due_decks_context.append({
                    'deck': deck,
                    'due_cards_count': due_cards_for_deck.count(),
                    'total_cards': deck.card_count 
                })
        return render(request, 'index.html', {"due_decks_data": due_decks_context})

@method_decorator(login_required, name='dispatch')
class DueDecksHTMLView(APIView):
    def get(self, request):
        due_decks_context = []
        decks = Deck.objects.filter(user=request.user)
        for deck in decks:
            due_cards_for_deck = deck.get_due_cards() 
            if due_cards_for_deck.exists():
                due_decks_context.append({
                    'deck': deck,
                    'due_cards_count': due_cards_for_deck.count(),
                    'total_cards': deck.card_count 
                })
        return render(request, 'due_decks.html', {'due_decks_data': due_decks_context})

def _clear_flashcard_session(session):
    session.pop(FLASHCARD_SESSION_DECK_ID, None)
    session.pop(FLASHCARD_SESSION_CARD_IDS, None)
    session.pop(FLASHCARD_SESSION_CURRENT_CARD_INDEX, None)

def _initialize_or_reset_deck_session(session, deck: Deck):
    session_cards_qs = deck.next_session(max_new_cards=10, max_review_cards=20)
    session[FLASHCARD_SESSION_CARD_IDS] = [card.id for card in session_cards_qs]
    session[FLASHCARD_SESSION_CURRENT_CARD_INDEX] = 0
    session[FLASHCARD_SESSION_DECK_ID] = deck.id
    session.modified = True

@login_required
def deck_session_view(request, deck_id):
    deck = get_object_or_404(Deck, id=deck_id, user=request.user)

    session_deck_id = request.session.get(FLASHCARD_SESSION_DECK_ID)
    session_card_ids = request.session.get(FLASHCARD_SESSION_CARD_IDS, [])

    if session_deck_id != deck_id or not session_card_ids:
        _initialize_or_reset_deck_session(request.session, deck)
        session_card_ids = request.session.get(FLASHCARD_SESSION_CARD_IDS, [])

    current_card_index = request.session.get(FLASHCARD_SESSION_CURRENT_CARD_INDEX, 0)

    if not session_card_ids or current_card_index >= len(session_card_ids):
        _clear_flashcard_session(request.session)
        return render(request, 'session_finished.html', {'deck': deck})

    try:
        current_card_id = session_card_ids[current_card_index]
        card = get_object_or_404(Card, id=current_card_id, deck=deck)
    except (IndexError, Card.DoesNotExist):
        logger.warning(f"Session inconsistency for user {request.user.id}, deck {deck_id}. Resetting session.")
        _clear_flashcard_session(request.session)
        return render(request, 'session_error.html', {'deck': deck, 'error_message': "Session error. Please try again."})

    total_cards = len(session_card_ids)
    progress_percent = int((current_card_index / total_cards) * 100)

    return render(request, 'session.html', {
        'deck': deck,
        'card': card,
        'progress_percent': progress_percent,
        'cards_done': current_card_index,
        'total_cards': total_cards
    })


@login_required
@require_http_methods(["POST"])
def update_card_view(request, pk): 
    session_deck_id = request.session.get(FLASHCARD_SESSION_DECK_ID)
    if not session_deck_id:
        return redirect('due_decks')

    deck = get_object_or_404(Deck, id=session_deck_id, user=request.user)
    card = get_object_or_404(Card, pk=pk, deck=deck)

    session_card_ids = request.session.get(FLASHCARD_SESSION_CARD_IDS, [])
    current_card_index = request.session.get(FLASHCARD_SESSION_CURRENT_CARD_INDEX)

    if current_card_index is None or not session_card_ids or \
       current_card_index >= len(session_card_ids) or \
       session_card_ids[current_card_index] != card.id:
        logger.warning(f"Card update attempt with inconsistent session for user {request.user.id}, card {pk}.")
        return redirect('deck_session', deck_id=deck.id)

    is_correct = request.POST.get('is_correct', 'false').lower() in ['true', '1', 'yes']
    card.update_performance(is_correct)

    request.session[FLASHCARD_SESSION_CURRENT_CARD_INDEX] = current_card_index + 1
    request.session.modified = True
    next_card_index = request.session[FLASHCARD_SESSION_CURRENT_CARD_INDEX]

    total_cards = len(session_card_ids)

    if next_card_index >= total_cards:
        _clear_flashcard_session(request.session)
        return render(request, 'partials/card_container.html')  # Optional: pass final progress here

    try:
        next_card_id = session_card_ids[next_card_index]
        next_card = get_object_or_404(Card, id=next_card_id, deck=deck)
    except (IndexError, Card.DoesNotExist):
        logger.error(f"Failed to fetch next card for user {request.user.id}, deck {deck.id} after advancing index.")
        _clear_flashcard_session(request.session)
        return render(request, 'partials/session_error_partial.html', {'deck': deck, 'error_message': "Error loading next card."})

    progress_percent = int((next_card_index / total_cards) * 100)

    return render(request, 'partials/card_container.html', {
        'card': next_card,
        'deck': deck,
        'progress_percent': progress_percent,
        'cards_done': next_card_index,
        'total_cards': total_cards
    })


@method_decorator(login_required, name='dispatch')
class ProfileView(APIView):
    def get(self, request):
        decks = Deck.objects.filter(user=request.user)
        decks_data = []
        total_progress_sum = 0

        for deck in decks:
            progress = deck.get_progress() 
            decks_data.append({
                'id': deck.id,
                'name': deck.name,
                'total_cards': deck.card_count, 
                'due_cards': deck.due_cards_count, 
                'progress': progress,
            })
            total_progress_sum += progress
        
        overall_progress = 0
        if decks.exists():
            overall_progress = round(total_progress_sum / decks.count())

        return render(request, 'profile.html', {
            'user': request.user,
            'decks_data': decks_data,
            'overall_progress': overall_progress,
        })

@method_decorator(login_required, name='dispatch')
class UploadDeckView(APIView):
    template_name = 'upload.html' 

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        anki_file = request.FILES.get('anki_file')
        if not anki_file:
            return render(request, self.template_name, {'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        if not anki_file.name.endswith('.apkg'):
             return render(request, self.template_name, {'error': 'Invalid file type. Please upload an .apkg file.'}, status=status.HTTP_400_BAD_REQUEST)


        importer = AnkiImporterService(user=request.user)
        try:
            importer.import_deck_from_file(anki_file)
            return redirect(reverse_lazy('profile'))
        except AnkiImportError as e:
            logger.warning(f"Anki import failed for user {request.user.id}: {e}")
            return render(request, self.template_name, {'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e: 
            logger.error(f"Unexpected error during Anki deck upload for user {request.user.id}: {e}", exc_info=True)
            return render(request, self.template_name, {'error': 'An unexpected server error occurred. Please try again.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
from django.shortcuts import render, redirect, get_object_or_404  
from django.conf import settings  
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from flashcards.models import Deck, Card
from .forms import LoginForm, RegisterForm
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from django.db import models
import tempfile
import os
import sqlite3
import zipfile
import json
from io import BytesIO
from django.db import transaction


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


def logout_view(request):
    logout(request)
    return redirect('login')


@method_decorator(login_required, name='dispatch')
class HomeView(APIView):
    def get(self, request):
        return render(request, 'index.html')
    

@method_decorator(login_required, name='dispatch')
class DueDecksHTMLView(APIView):
    def get(self, request):
        decks = Deck.objects.filter(user=request.user)
        context = []
        for deck in decks:
            cards = deck.cards.filter(next_review__lte=timezone.now())
            if cards.exists():  # Garante que há cartas vencidas antes de adicionar
                print(deck.id)
                context.append({'deck': deck, 'cards': cards, 'total_cards' : deck.cards.count()})

        return render(request, 'decks.html', {'due_decks': context})   


@login_required
def deck_session(request, deck_id):
    # Validate deck exists and belongs to user
    deck = get_object_or_404(Deck, id=deck_id, user=request.user)
    
    # Initialize session with safe defaults
    request.session.setdefault('session_cards', [])
    request.session.setdefault('current_card_index', 0)
    request.session.setdefault('deck_id', deck_id)
    
    # Reset session if deck changed or no cards remaining
    if (request.session['deck_id'] != deck_id or 
        not request.session['session_cards']):
        session_cards = deck.next_session(max_new_cards=10, max_review_cards=15)
        request.session['session_cards'] = [card.id for card in session_cards]
        request.session['current_card_index'] = 0
        request.session['deck_id'] = deck_id

    try:
        current_index = request.session['current_card_index']
        card_id = request.session['session_cards'][current_index]
        card = Card.objects.get(id=card_id, deck=deck)
    except (IndexError, Card.DoesNotExist):
        # Clear invalid session data
        request.session.pop('session_cards', None)
        request.session.pop('current_card_index', None)
        request.session.pop('deck_id', None)
        return render(request, 'session.html', {'deck': deck})

    return render(request, 'session.html', {'deck': deck, 'card': card})

@require_http_methods(["POST"])
@login_required
def update_card(request, pk):
    # Get current deck ID from session
    deck_id = request.session.get('deck_id')    
        
    # Validate deck exists and belongs to user
    deck = get_object_or_404(Deck, id=deck_id, user=request.user)
    card = get_object_or_404(Card, id=pk, deck=deck)
    
    # Validate session state
    if ('current_card_index' not in request.session or 
        'session_cards' not in request.session):
        return redirect('deck_session', deck_id=deck_id)
        
    current_index = request.session['current_card_index']
    session_card_ids = request.session['session_cards']
    
    # Verify card is in correct sequence
    if current_index >= len(session_card_ids) or card.id != session_card_ids[current_index]:
        return redirect('deck_session', deck_id=deck_id)
        
    # Update card performance
    is_correct = request.POST.get('is_correct', 'false').lower() in ['true', '1', 'yes']
    card.update_performance(is_correct)
    
    # Move to next card
    request.session['current_card_index'] = current_index + 1
    next_index = request.session['current_card_index']
    
    try:
        next_card_id = session_card_ids[next_index]
        next_card = Card.objects.get(id=next_card_id, deck=deck)
    except (IndexError, Card.DoesNotExist):
        # Clear session data when done
        request.session.pop('session_cards', None)
        request.session.pop('current_card_index', None)
        request.session.pop('deck_id', None)
        return render(request, 'partials/empty_state.html', {'deck': deck})
    
    return render(request, 'card_container.html', {'card': next_card, 'deck': deck})

@method_decorator(login_required, name='dispatch')
class ProfileView(APIView):
    def get(self, request):
        decks = Deck.objects.filter(user=request.user)
        total_progress = 0

        # Iterate over each deck to compute necessary details.
        for deck in decks:
            # Count all cards in this deck.
            deck.total_cards = deck.cards.count()
            # Count cards that are due for review.
            deck.due_cards = deck.cards.filter(next_review__lte=timezone.now()).count()
            # Get the progress for this deck.
            progress = deck.get_progress()
            # You can also store the progress directly on the deck object
            # so that the template can use it as {{ deck.get_progress }}.
            deck.progress = progress
            total_progress += progress

        # Calculate overall progress (average progress across decks).
        if decks.exists():
            overall_progress = total_progress / decks.count()
        else:
            overall_progress = 0

        return render(request, 'profile.html', {
            'user': request.user,
            'decks': decks,
            'total_progress': overall_progress,
        })

@method_decorator(login_required, name='dispatch')
class UploadDeckView(APIView):
    def post(self, request):
        if 'anki_file' not in request.FILES:
            return render(request, 'upload.html', {'error': 'No file uploaded'})

        tmp_path = None
        db_tmp_path = None  # Path for temporary SQLite DB file
        try:
            # Save uploaded file to a temporary file
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                for chunk in request.FILES['anki_file'].chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            # Process the .apkg file (a ZIP archive)
            with zipfile.ZipFile(tmp_path) as z:
                # Look for the collection file (supports Anki 2.1+)
                collection_files = [f for f in z.namelist() if f.endswith('.anki2')]
                if not collection_files:
                    raise ValueError("Invalid Anki package - missing collection file")
                
                # Extract the collection database content
                with z.open(collection_files[0]) as f:
                    db_content = f.read()
                
                # Write the collection database content to a temporary file
                with tempfile.NamedTemporaryFile(delete=False) as db_tmp:
                    db_tmp.write(db_content)
                    db_tmp.flush()
                    db_tmp_path = db_tmp.name

            # Open the extracted SQLite database
            conn = sqlite3.connect(db_tmp_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Retrieve models from the collection
            cursor.execute("SELECT models FROM col")
            col_row = cursor.fetchone()
            if not col_row:
                raise ValueError("Invalid Anki package - missing collection data")
            models = json.loads(col_row['models'])
            valid_models = self.validate_models(models)
            if not valid_models:
                raise ValueError("Deck must contain Chinese characters (Hanzi) and pinyin fields")

            # Convert model IDs to int for type consistency
            valid_model_ids = [int(model['model_id']) for model in valid_models]
            placeholders = ','.join(['?'] * len(valid_model_ids))
            cursor.execute(
                f"SELECT * FROM notes WHERE mid IN ({placeholders})",
                valid_model_ids
            )
            notes = cursor.fetchall()
            conn.close()

            # Create the deck and process each note within a transaction
            with transaction.atomic():
                deck = Deck.objects.create(
                    user=request.user,
                    name=os.path.splitext(request.FILES['anki_file'].name)[0]
                )
                for note in notes:
                    self.process_note(note, valid_models, deck)

            return redirect('profile')

        except Exception as e:
            error_message = (
                "Failed to process Anki deck. Please ensure: "
                "1. The file is a valid Anki .apkg package; "
                "2. It contains fields named: Hanzi, Pinyin, and English; "
                "3. It has at least one note. "
                f"Error details: {str(e)}"
            )
            return render(request, 'upload.html', {'error': error_message})

        finally:
            # Clean up temporary files
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            if db_tmp_path and os.path.exists(db_tmp_path):
                os.unlink(db_tmp_path)

    def validate_models(self, models):
        valid_models = []
        for mid, model in models.items():
            # Extract field names from the model definition
            field_names = [f['name'] for f in model['flds']]
            # Convert field names to lowercase for case-insensitive matching
            fields_lower = [f.lower() for f in field_names]
            # Define accepted variations for each required field
            required_fields = {
                'chinese': ['hanzi', 'character', 'simplified', 'zi', 'chinese'],
                'pinyin': ['pinyin', 'pronunciation', 'reading'],
                'translation': ['english', 'translation', 'meaning']
            }
            field_map = {}
            for field_type, variations in required_fields.items():
                for i, f in enumerate(fields_lower):
                    if f in variations:
                        field_map[field_type] = i  # Map field type to its index
                        break
                else:
                    # If a required field isn't found, skip this model
                    break
            else:
                valid_models.append({
                    'model_id': mid,
                    'field_map': field_map,
                    'field_names': field_names
                })
        return valid_models

    def process_note(self, note, valid_models, deck):
        try:
            # Split note fields using Anki's field separator
            fields = note['flds'].split('\x1f')
            note_mid = int(note['mid'])
            for model in valid_models:
                if note_mid == int(model['model_id']):
                    mapping = model['field_map']
                    try:
                        character = fields[mapping['chinese']].strip()
                        pinyin = fields[mapping['pinyin']].strip()
                        translation = fields[mapping['translation']].strip()
                    except IndexError:
                        # Skip if field indices are out of range
                        continue

                    # Skip cards missing required fields
                    if not character or not pinyin:
                        continue

                    # Create the card
                    Card.objects.create(
                        deck=deck,
                        character=character,
                        pinyin=pinyin,
                        translation=translation
                    )
                    break  # Found the matching model; no need to check others
        except (IndexError, KeyError, ValueError):
            # Skip any note that doesn't meet the criteria
            pass

    def get(self, request):
        return render(request, 'upload.html')
    
    

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Deck(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='decks'
    )

    @property
    def card_count(self):
        """Returns the total number of cards in this deck."""
        return self.cards.count()

    def get_due_cards(self):
        """Returns a queryset of cards that are due for review."""
        return self.cards.filter(next_review__lte=timezone.now())

    @property
    def due_cards_count(self):
        """Returns the count of cards due for review."""
        return self.get_due_cards().count()

    def get_progress(self):
        total_cards = self.cards.count()
        if total_cards == 0:
            return 0
        # You might decide to use seen cards rather than cards due for review.
        reviewed_cards = self.cards.filter(seen=True).count()
        return int((reviewed_cards / total_cards) * 100)

    def seen_cards(self):
        """
        Returns all cards that have been seen (reviewed) by the user.
        """
        return self.cards.filter(seen=True)

    def next_session(self, max_new_cards=10, max_review_cards=15):
        now = timezone.now()
        review_cards = self.cards.filter(next_review__lte=now, seen=True)[:max_review_cards]
        new_cards = self.cards.filter(seen=False)[:max_new_cards]
        return list(review_cards) + list(new_cards)

    def __str__(self):
        return f'{self.name} ({self.user.username})'


class Card(models.Model):
    deck = models.ForeignKey(
        Deck, on_delete=models.CASCADE, related_name='cards'
    )
    character = models.CharField(max_length=10)
    pinyin = models.CharField(max_length=50)
    translation = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    next_review = models.DateTimeField(default=timezone.now)
    consecutive_correct = models.IntegerField(default=0)
    # New field to track whether the user has seen this card before.
    seen = models.BooleanField(default=False)

    def update_performance(self, is_correct):
        """
        Updates the card's scheduling based on the user's performance.
        Marks the card as seen if it wasn't already.
        """
        now = timezone.now()
        # Mark card as seen if it's the first time the card is reviewed.
        if not self.seen:
            self.seen = True

        if is_correct:
            self.consecutive_correct += 1
            interval = self.consecutive_correct ** 2  # Success squared
        else:
            self.consecutive_correct = 0
            interval = 1  # Reset interval to 1 day on failure

        # Ensure the interval does not exceed 60 days.
        interval = min(interval, 60)
        self.next_review = now + timedelta(days=interval)
        self.save()

    def __str__(self):
        return f'{self.character} ({self.deck.name})'

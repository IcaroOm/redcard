from rest_framework import serializers
from .models import Deck, Card
from django.utils import timezone


class CardSerializer(serializers.ModelSerializer):
    deck = serializers.PrimaryKeyRelatedField(
        queryset=Deck.objects.all(), write_only=True
    )

    class Meta:
        model = Card
        fields = [
            'id',
            'deck',
            'character',
            'pinyin',
            'translation',
            'created_at',
            'next_review',
            'consecutive_correct',
        ]
        read_only_fields = ['created_at', 'next_review', 'consecutive_correct']

    def validate_deck(self, value):
        """Ensure the deck belongs to the requesting user"""
        if value.user != self.context['request'].user:
            raise serializers.ValidationError("You don't own this deck.")
        return value


class DeckSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    total_cards = serializers.SerializerMethodField()
    due_cards = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()

    class Meta:
        model = Deck
        fields = [
            'id',
            'user',
            'name',
            'description',
            'created_at',
            'updated_at',
            'total_cards',
            'due_cards',
            'progress',
        ]
        read_only_fields = [
            'created_at',
            'updated_at',
            'total_cards',
            'due_cards',
            'progress',
        ]

    def get_total_cards(self, obj):
        return obj.cards.count()

    def get_due_cards(self, obj):
        return obj.cards.filter(next_review__lte=timezone.now()).count()

    def get_progress(self, obj):
        return obj.get_progress()


class DeckDetailSerializer(DeckSerializer):
    cards = CardSerializer(many=True, read_only=True)

    class Meta(DeckSerializer.Meta):
        fields = DeckSerializer.Meta.fields + ['cards']

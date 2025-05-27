from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Deck, Card
from .serializers import CardSerializer


class DueFlashcardsView(APIView):
    """
    GET endpoint that returns cards due for review from user's decks
    Accepts 'limit' query parameter to limit results (default: 10)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get and validate limit parameter
        limit = request.query_params.get('limit', '10')
        try:
            limit = int(limit)
        except ValueError:
            return Response(
                {'error': 'Limit must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get due cards from user's decks
        due_cards = Card.objects.filter(
            deck__user=request.user, next_review__lte=timezone.now()
        ).order_by('next_review')[:limit]

        serializer = CardSerializer(due_cards, many=True)
        return Response(
            {
                'count': due_cards.count(),
                'next_review': due_cards.first().next_review
                if due_cards
                else None,
                'results': serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class UpdatePerformanceView(APIView):
    """
    POST endpoint that updates a card's performance
    Requires authentication and card ownership
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            # Get card ensuring it belongs to the user
            card = Card.objects.get(pk=pk, deck__user=request.user)
        except Card.DoesNotExist:
            return Response(
                {'error': 'Card not found.'}, status=status.HTTP_404_NOT_FOUND
            )

        # Validate is_correct parameter
        is_correct = request.data.get('is_correct')
        if is_correct is None:
            return Response(
                {'error': 'Missing "is_correct" field.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Handle different truthy values
        if isinstance(is_correct, str):
            is_correct = is_correct.lower() in ['true', '1', 'yes', 'y']
        elif not isinstance(is_correct, bool):
            return Response(
                {'error': 'Invalid "is_correct" format.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update and return response
        card.update_performance(is_correct)
        serializer = CardSerializer(card)
        return Response(serializer.data, status=status.HTTP_200_OK)

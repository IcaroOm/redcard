from django.contrib import admin
from .models import Deck, Card


class CardInline(admin.TabularInline):
    model = Card
    extra = 1
    fields = (
        'character',
        'pinyin',
        'translation',
        'next_review',
        'consecutive_correct',
    )
    readonly_fields = ('next_review', 'consecutive_correct')
    show_change_link = True


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'created_at', 'card_count', 'progress')
    list_filter = ('created_at', 'user')
    search_fields = ('name', 'description', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CardInline]

    fieldsets = (
        (None, {'fields': ('user', 'name', 'description')}),
        (
            'Timestamps',
            {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)},
        ),
    )

    def card_count(self, obj):
        return obj.cards.count()

    card_count.short_description = 'Cards'

    def progress(self, obj):
        return f'{obj.get_progress()}%'

    progress.short_description = 'Progress'


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = (
        'character',
        'pinyin',
        'translation_short',
        'deck',
        'next_review',
        'consecutive_correct',
    )
    list_filter = ('deck', 'next_review')
    search_fields = ('character', 'pinyin', 'translation', 'deck__name')
    readonly_fields = ('created_at',)
    date_hierarchy = 'next_review'

    fieldsets = (
        (None, {'fields': ('deck', 'character', 'pinyin', 'translation')}),
        (
            'Review Information',
            {
                'fields': ('next_review', 'consecutive_correct'),
                'classes': ('collapse',),
            },
        ),
        ('Timestamps', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )

    def translation_short(self, obj):
        return (
            obj.translation[:50] + '...'
            if len(obj.translation) > 50
            else obj.translation
        )

    translation_short.short_description = 'Translation'

# Mandarin Flashcard App

A small Django project I built for fun — it's like a tiny, custom Anki deck for Mandarin learners.

This app helps you practice Chinese characters using a flashcard interface with session-based progress tracking. It's not meant to be polished or widely used — just an experiment to try out Django sessions, HTMX for dynamic updates, and Tailwind for a clean UI.

## Features

-  Flashcard sessions with progress tracking
-  HTMX-powered updates — no page reloads!
-  Progress bar that updates as you go
-  Upload your own Anki decks — it might have some weird artifacts in the Pinyin though
-  Login required

## Coming Soon (maybe)

-  Text-to-Speech (TTS) for Pinyin
-  More intelligent deck filtering / spaced repetition

## Setup

```bash
git clone https://github.com/your-username/mandarin-flashcards.git
cd mandarin-flashcards
poetry install
make migrate
poetry run python manage.py createsuperuser
make run
````

## Tech Stack

* Django
* HTMX
* Tailwind CSS
* SQLite (for now)

## Why?

I just wanted to mess around with:

* Django sessions & custom logic
* HTMX partial rendering
* A bit of Chinese character practice

## License

MIT – do whatever you want.

```
---

Let me know if you'd like help integrating a Python TTS engine like `gTTS` or `pyttsx3` next.
```

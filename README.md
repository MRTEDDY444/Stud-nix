# Student Hub — Stage 1 MVP

An all-in-one student platform: search any subject and get AI-organized
study notes built from real, cited web sources — no admin uploads required.
Plus a working set of student calculators.

This is the **Stage 1 MVP** from the build plan: homepage, search flow,
AI study notes, source citations (web/PDF/video), and the calculator
toolkit. It runs end-to-end right now using mock search/AI providers, and
is structured so real providers drop in by changing `.env` only.

## What actually works right now

- Homepage with search + example queries
- `/search?q=...` → calls the search service → generates structured AI
  study notes → renders notes + cited web/PDF/video resources
- AI Study Helper buttons (Explain, Simplify, MCQs, Flashcards, Exam
  notes, Summarize) via `/api/ai-helper`
- GPA/CGPA, Percentage, Attendance, Age, Unit Converter, and Scientific
  calculators — all fully functional client-side
- Dark/light mode, mobile-first responsive layout
- SQLite logging of searches (`searches` table); schema for users, notes,
  and saved resources is defined and ready for Stage 5 (auth)
- Custom 404/500 pages — no stack traces shown to users

## Running it

```bash
cd student-hub
python -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Visit `http://localhost:5000`.

By default `SEARCH_API_PROVIDER=mock` and `AI_API_PROVIDER=mock`, so the
whole search → notes → citations flow works with **zero external API
keys**, using clearly-labeled placeholder data (see the "MOCK PROVIDER"
sections in `services/search_service.py` and `services/ai_service.py`).

## Wiring in real APIs

Edit `.env` (never commit it):

```
SEARCH_API_KEY=your-real-key
SEARCH_API_PROVIDER=brave      # or serper | tavily | bing
AI_API_KEY=your-real-key
AI_API_PROVIDER=anthropic
```

`services/search_service.py` already has request/response mapping stubs
for Brave, Serper, Tavily, and Bing — pick one, confirm the field mapping
against that provider's current docs, and it's live. Same pattern in
`services/ai_service.py` for the Anthropic Messages API.

Keys are read server-side only (`config/config.py` via environment
variables) and are never sent to the browser.

## Copyright approach

The AI notes are a **transformation**, not a copy: `ai_service.py`
generates structured, student-friendly notes (definition, steps, example,
complexity, exam points, practice questions) and every search result page
keeps the original source links visible and clickable next to the notes.
PDFs are linked to their original, publicly accessible location — never
downloaded and rehosted.

## Project structure

```
student-hub/
├── app.py                  # Flask app factory
├── config/config.py        # env-driven config
├── routes/
│   ├── main.py              # homepage, calculators page
│   └── search.py            # search + AI notes + AI helper API
├── services/
│   ├── search_service.py    # web search — mock + 4 real-provider stubs
│   └── ai_service.py        # AI notes/helper — mock + Anthropic stub
├── models/models.py        # SQLAlchemy models (searches wired in now;
│                            #  users/notes/saved_resources ready for later)
├── templates/               # Jinja templates
└── static/{css,js}/         # design system + calculators + AI helper JS
```

## Next stages (not yet built, per the original plan)

- Stage 2: richer AI helper (flashcard UI, MCQ quiz mode)
- Stage 4: Study Timetable, Resume Builder, Notes Organizer, PDF/Coding tools
- Stage 5: Auth + student dashboard (models are already defined)
- Stage 6: Admin dashboard, analytics, monetization
- Stage 7: Deployment, SEO, production hardening

Build without breaking Stage 1 — each new blueprint/service should be
additive, following the same mock-first, provider-swappable pattern.

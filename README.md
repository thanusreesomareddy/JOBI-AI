# Jobi AI API

Backend for resume ingestion, role/skills detection, and N-day training plan generation.

## Stack

- **FastAPI** — HTTP API
- **PyMuPDF** — PDF text extraction
- **Claude** — role detection + plan generation + answer evaluation
- **Deepgram** (default) or **OpenAI Whisper** — server speech-to-text
- **Browser speech** (Chrome/Edge) — free fallback, no STT API key
- **Supabase** — Postgres persistence

## Setup

1. Create a Supabase project and run migrations in the SQL editor:
   - `supabase/migrations/001_initial.sql`
   - `supabase/migrations/002_sessions.sql`
   - `supabase/migrations/003_session_followups.sql`
   - `supabase/migrations/004_plan_adaptation.sql`
   - `supabase/migrations/005_session_adapt_plan.sql`
   - `supabase/migrations/006_interview_mode.sql`
   - `supabase/migrations/007_interview_phase.sql`
   - `supabase/migrations/008_interviewer_name.sql`

2. Copy env template and fill keys:

   ```powershell
   cd C:\Users\somar\Projects\jobi-ai
   copy .env.example .env
   ```

   - `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)
   - `DEEPGRAM_API_KEY` — from [console.deepgram.com](https://console.deepgram.com) (recommended STT; free credits on signup)
   - Optional: `STT_PROVIDER=openai` + `OPENAI_API_KEY` for Whisper instead
   - `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` — Project Settings → API (service_role, not anon)

3. Install and run:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

4. Open the app:
   - **User UI:** http://127.0.0.1:8000
   - **API docs (developers):** http://127.0.0.1:8000/docs

## API flow (your pipeline)

| Step | Endpoint | What it does |
|------|----------|----------------|
| 1 | `POST /resume/upload` | PDF → text → `resumes` row |
| 2 | `POST /resume/{resume_id}/analyze` | LLM → `parsed_json` (role, skills, gaps) |
| 3 | `POST /plans/generate?resume_id=...` | LLM → N-day plan → `plans` row |
| 4 | `GET /plans/candidate/{candidate_id}` | Fetch latest plan |

## Practice session flow (text)

| Step | Endpoint | What it does |
|------|----------|----------------|
| 5 | `POST /session/start` | Start Day N — returns reading + first question |
| 6 | `POST /session/{session_id}/answer` | Submit text answer → score + feedback → next question |
| 7 | `POST /session/{session_id}/answer-audio` | Upload voice recording → transcribe → evaluate |
| 8 | `GET /session/{session_id}` | Session state + turn history |
| 9 | `GET /progress/candidate/{candidate_id}` | Day completion status + scores |

**Dynamic questions:** Q1 from day context; Q2+ adapt to your answers (up to 4 per session).

**Plan adaptation (Layer 6):** Optional — enable **Personalize upcoming days** on the plan screen before practice. When on, completing a day revises later days from your scores; personalized days show a ✨ badge. Adaptation uses all completed sessions and recurring focus areas.

**Coaching features:** Focus areas dashboard on the plan screen; skip reading; practice again on completed days (tracks attempts and best score).

**Live interview mode:** AI interviewer avatar (male/female matches voice), tap mic to join, greeting phase then formal Q&A. Pause/resume/end controls in the UI. Endpoints: `POST /session/{id}/interview-begin`, `POST /session/{id}/interview-turn`, `POST /session/{id}/interview-end` (scores + summary).

`GET /health` reports whether Supabase and Anthropic env vars are set.

## Project layout

```
app/
  main.py              # FastAPI app
  config.py            # Settings from .env
  models/              # Pydantic contracts (ParsedResume, TrainingPlan)
  routers/             # resume, plans, session endpoints
  services/            # parser, LLM, Supabase
supabase/migrations/   # SQL schema
```

## Voice

- **STT:** Browser speech (Chrome/Edge, free) or Deepgram/OpenAI via `STT_PROVIDER`
- **TTS:** Browser speech synthesis in the practice UI — coach reads questions and feedback (toggle **Coach speaks**)

## Next steps

- Supabase Auth + RLS per user
- Deploy API to a host (Railway, Render, Fly.io)
- Optional: ElevenLabs for higher-quality TTS

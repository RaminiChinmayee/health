# HealthAssist AI — Personal Health & Lifestyle Assistant

React + FastAPI + PostgreSQL implementation of the IJRIAS 2026 paper *AI-Based Personal Health & Lifestyle Assistant*, extended with authentication, user history, persistent chatbot memory, 11 languages, and a multimodal chatbot.

> HealthAssist AI gives general health information. It is not a medical device and does not diagnose.

## Build status

| Phase | Scope | Status |
|---|---|---|
| 1 | Backend, database, authentication, profile, account management | **Done:** API complete, 29 tests passing |
| 2 | Homepage, React app shell, profile dropdown, auth pages, 11-language i18n | **Done:** 9 browser end-to-end tests passing. Translations still need native-speaker review ([docs/translation-review.md](docs/translation-review.md)) |
| 3 | Symptom / diabetes / heart / Parkinson's models, prediction history, hospital finder, diet planner | **Done:** 47 backend and 14 browser tests passing. Model results are in [ml/EVALUATION.md](ml/EVALUATION.md) |
| 4 | Chatbot (Gemini), 3-level memory, voice (STT/TTS), multilingual chat | **Done:** 75 backend and 22 browser tests passing. Evaluations are summarised in [ml/EVALUATION.md](ml/EVALUATION.md) |
| 5 | Skin-lesion image model (HAM10000), image upload in chat, image history, evaluation report | **Done:** EfficientNet-B0, test accuracy 81.6% / macro-F1 0.659 / macro ROC-AUC 0.940 on 1431 held-out images ([report](ml/artifacts/skin/1.0.0/report.md)). 84 backend and 25 browser tests passing in total |

## Setup

### 1. PostgreSQL (one-time, needs sudo)

```bash
sudo -u postgres psql -c "CREATE ROLE healthai LOGIN PASSWORD 'choose-a-password';"
sudo -u postgres psql -c "CREATE DATABASE healthai OWNER healthai;"
sudo -u postgres psql -c "CREATE DATABASE healthai_test OWNER healthai;"
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt      # add -dev for tests/training
cp .env.example .env        # then set DATABASE_URL, JWT_SECRET, GEMINI_API_KEY, and optionally SMTP / Google
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/api/docs

The first start needs internet: the multilingual retrieval model (about 470 MB) downloads once. The trained health models (`ml/artifacts/`) and the MedlinePlus knowledge base (`backend/app/data/kb/`) are already in the repository. Keep `scikit-learn` at the pinned version, because the saved models were created with it.

### 3. Frontend

```bash
source ~/.nvm/nvm.sh            # Node 22 via nvm
cd frontend && npm install
npm run dev                     # http://localhost:5173  (proxies /api to :8000)
```

### 4. Tests

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://healthai:PASSWORD@127.0.0.1:5432/healthai_test .venv/bin/pytest -q
```

Browser end-to-end tests run against the real stack. They register many throwaway accounts, so **always start the backend in console-email mode for tests**, or real verification emails will be sent from your SMTP account. The tests refuse to run otherwise.

```bash
cd backend && EMAIL_BACKEND=console FRONTEND_URL=http://localhost:5173 .venv/bin/uvicorn app.main:app --port 8000 > /tmp/backend.log 2>&1 &
```

Then:

```bash
cd frontend
PW_CHANNEL=chrome BACKEND_LOG=/path/to/backend.log npx playwright test
```

`PW_CHANNEL=chrome` uses the installed Google Chrome. Omit it after running `npx playwright install chromium`.

The backend tests send real SMTP traffic to a local in-process mail server. Only Google's token endpoint and its ID-token signature check are stubbed, because those require Google's servers.

## What still needs your credentials

| Feature | Setting | Without it |
|---|---|---|
| Email verification, password reset, security alerts | `EMAIL_BACKEND=smtp` + `SMTP_*` | Emails are **not sent**. Links are printed in the server log, and the API reports `email_delivery: "not_configured"`. |
| Continue with Google | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | `/api/auth/google` returns 503, and the frontend hides the button. |
| Chatbot, speech-to-text, text-to-speech | `GEMINI_API_KEY` | The chatbot reports that it is unavailable, and voice falls back to the browser's own speech features. |
| Hospital finder | none (public OpenStreetMap servers) | Public servers are often overloaded; in live tests some cities timed out. The page then offers a Google Maps search link. For production, run your own Overpass server or use a paid places API. |

Real delivery through a hosted email provider and a real Google sign-in have **not** been tested yet, because no credentials exist. Test both once you have added them.

## Phase 1 security design

- **Passwords:** Argon2id. Rules: at least 10 characters and 3 character classes, plus a zxcvbn score of 3 or more, checked against the user's own name, email, and birth year.
- **Sessions:** 15-minute JWT access tokens are held in memory by the SPA. The refresh token is opaque, stored only as a SHA-256 hash, and sent in an httpOnly, SameSite=Lax cookie scoped to `/api/auth`. Every refresh rotates the token. Replaying an old refresh token revokes the whole session family. Access tokens are checked against their session on every request, so logout and password changes take effect immediately.
- **CSRF:** cookie-authenticated endpoints (`/refresh`, `/logout`) require an `X-HealthAI-CSRF` header.
- **Email verification and password reset tokens:** 256-bit random values, stored as hashes, single-use, short expiry (24 h and 30 min). Only the newest reset link works. Reset responses are identical whether or not the account exists. A completed reset revokes all sessions.
- **Rate limiting:** stored in the database (`account_security_events`), so it works across workers. Applies to login, registration, password reset, verification resend, and password change.
- **Google OAuth:** authorization-code flow with PKCE, `state`, and `nonce` held in a signed short-lived cookie. The ID token is verified on the backend. Account-linking rules prevent takeover:
  - Google must assert that the email is verified.
  - An existing verified local account is linked, and the user gets a security alert.
  - An existing *unverified* local account has its unproven password removed before linking, because someone else may have pre-registered the address.
- **Data isolation:** every `/api/profile/*` endpoint acts only on the authenticated user. No endpoint takes a user ID from the client.
- **Avatars:** decoded with Pillow and re-encoded to WebP, which strips EXIF and GPS data. Stored outside any static directory and served only to their owner.

## Machine-learning models (Phase 3)

Training code and datasets are in [ml/](ml/). Every reported number is computed by the scripts; see [ml/EVALUATION.md](ml/EVALUATION.md).

```bash
cd ml
# datasets download to ml/data/raw (UCI, OpenML, USDA; see each train_*.py for sources)
../backend/.venv/bin/python train_heart.py              # also: train_diabetes.py, train_diabetes_symptoms.py,
../backend/.venv/bin/python train_parkinsons.py         #       train_symptoms.py
../backend/.venv/bin/python build_nutrition.py          # diet planner food database
../backend/.venv/bin/python summarize.py                # regenerates EVALUATION.md
```

Key findings from evaluation:
- **Symptom dataset:** synthetic. 4,920 rows contain only 305 unique patterns, and its published test file overlaps its training file. Scores were measured after removing duplicates, and the UI shows match strength, not percentages.
- **Early-stage diabetes dataset:** 269 of 520 rows are exact duplicates, which were removed before evaluation.
- **Parkinson's:** the commonly used Oxford dataset (31 people) was **rejected**. Split by person, it identified 0% of healthy test subjects. The deployed model uses Sakar et al. (252 people) and is weak (test ROC-AUC 0.70). It is shown as "voice pattern resembles group X", never as a risk percentage.
- The paper's accuracy figures (92% and others) are not reproduced or claimed anywhere.

## Chatbot (Phase 4)

- **Answers:** Gemini (`gemini-3.5-flash`). If that model is overloaded or rate-limited before any text has streamed, the app falls back to `gemini-3.5-flash-lite`. Replies stream over Server-Sent Events.
- **Grounding:** passages from MedlinePlus (1,017 health topics, 2,233 passages), retrieved with a **local** multilingual embedding model (`intfloat/multilingual-e5-small`). That means no API quota is used and questions aren't sent anywhere for retrieval. Answers cite passages as [1], [2], and citation numbers that don't match a retrieved passage are removed. Rebuild the index with `ml/build_knowledge.py`.
- **Memory levels:**
  1. Recent messages, kept within a token budget.
  2. Long-term memory, **opt-in only**. Health details wait as "pending" until the user confirms them, and expire after 365 days. Everything can be reviewed, edited, disabled or deleted at `/chat/memory`.
  3. Automatic summaries of long conversations, plus summaries of the user's own earlier chats when memory is on.
- **Safety:** a multilingual keyword pre-check shows an emergency banner (112) or a self-harm banner (Tele-MANAS 14416). The model is also instructed not to diagnose or give prescription doses.
- **Voice:**
  - The browser records WAV audio itself, so no server transcoding is needed.
  - Speech-to-text uses `gemini-3.5-transcribe`, then `gemini-3.5-flash-lite` once that model's 25-a-day free quota runs out. The browser's own speech recognition is offered as a last resort.
  - The transcript is shown for editing before it's sent.
  - Text-to-speech uses `gemini-3.8-flash-tts`, falling back to the browser's built-in voices.
- **Parkinson's from a recording (experimental):** Praat, via parselmouth, measures the model's 15 voice features from a sustained "aaa" recording. Recordings outside the study's measured range are refused, and the audio is not stored.

**Free-tier limits found during development:** the transcription model allows 25 requests a day, and `gemini-embedding-2` has a small daily limit, which is why retrieval runs locally. Google Search grounding isn't included. A paid key removes these limits.

## Future work

- **Skin-image model:** retrain on more diverse data (ISIC, darker skin tones, phone photos), evaluate the non-skin rejection on real everyday photos, and improve the rarer categories (actinic keratosis sensitivity is 32.6%).
- **Better retrieval for Indian-language questions:** retrieval quality is weak today ([ml/eval/retrieval.md](ml/eval/retrieval.md)). Try a larger embedding model, translate questions to English before retrieval, and add re-ranking.
- **Clinician and native-speaker review** of model explanations, chatbot answers (`ml/eval/chat_review_sheet.csv`) and translations (`docs/translation-review.md`).
- **Production:** a paid Gemini tier (free-tier daily limits are low), your own Overpass server or a paid places API, and real SMTP and Google OAuth credentials.

A presentation walkthrough is in [docs/DEMO.md](docs/DEMO.md).

<!-- # BakiClear

**AI-Powered Collections Strategy & Negotiation** — Razorpay AI Buildathon 2026.

> BakiClear doesn't just remind customers to pay. It decides *how* each overdue
> payment should be recovered, negotiates within merchant-defined limits, and
> turns commitments into tracked payments.

**Core principle: LLM proposes. Policy decides. Backend executes. Database records.**

## Layout

| Path | Owner | Contents |
|---|---|---|
| `ai/` | Person 2 | Agents, orchestration, guardrails, schemas, prompts, voice |
| `frontend/` | Person 2 | Streamlit demo app |
| `backend/` | Person 1 | FastAPI, SQLAlchemy models, migrations, seed data |
| `data/` | shared | Mock fixtures for offline AI runs |
| `tests/` | shared | Pytest suites |
| `docs/` | shared | Architecture notes |

## Setup

```bash
uv venv --python 3.12
uv sync --group dev
cp .env.example .env      # then add your GEMINI_API_KEY
```

Run anything with `uv run <cmd>` (no manual venv activation needed).

## Branches

- `main` — integration
- `ai-engine` — Person 2
- `backend-core` — Person 1

## Stack notes (verified 2026-09-05)

- Gemini via `google-genai` (the `google-generativeai` package is **deprecated**).
- Structured output uses `client.models.generate_content(...,
  config=types.GenerateContentConfig(response_mime_type="application/json",
  response_schema=SomePydanticModel))` and reads `response.parsed`.
- Default model `gemini-3.5-flash`, overridable via `GEMINI_MODEL`. -->

## License & Usage

BakiClear is an independent prototype developed for the Razorpay AI
Buildathon 2026.

This repository is publicly available for hackathon evaluation, review,
demonstration, and educational reference.

The source code is not licensed for commercial use, redistribution,
sublicensing, or creation of derivative products without explicit
permission from the copyright holders.

See [LICENSE.md](LICENSE.md) for complete terms.

BakiClear is not an official Razorpay product. Razorpay trademarks,
services, APIs, SDKs, and other intellectual property remain the property
of their respective owners.
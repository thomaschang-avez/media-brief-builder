# Media Brief Builder

Automated media brief generator for PR teams. A Google Form submission triggers a Flask webhook, which kicks off a 5-agent CrewAI pipeline that gathers reporter and client intelligence, assembles a formatted brief, runs deterministic QA, creates a Google Doc, and delivers it via Slack — all in under 5 minutes.

## Architecture

```
Google Form → Apps Script → POST /brief
                                  ↓
                         Flask webhook (202 fire-and-forget)
                                  ↓
              ┌───────────────────────────────────────┐
              │           CrewAI Pipeline             │
              │                                       │
              │  Agent 1: Reporter Intelligence       │
              │    → scrape reporter page             │
              │    → extract headshot, bio, coverage  │
              │    → Glean search as fallback         │
              │                                       │
              │  Agent 2: Client Memory Bank          │
              │    → 6× Glean searches                │
              │    → extract talking points verbatim  │
              │    → pull boilerplate + FAQ           │
              │                                       │
              │  Agent 3: News Desk                   │
              │    → Serper news search               │
              │    → 3 relevant articles + bullets    │
              │                                       │
              │  Agent 4: Senior PR Strategist        │
              │    → assemble full brief JSON         │
              │    → opportunity, Q&A, logistics      │
              │                                       │
              │  Agent 5: QA (deterministic Python)   │
              │    → validate schema, counts, labels  │
              │    → no LLM — instant and reliable    │
              └───────────────────────────────────────┘
                                  ↓
                    brief_builder.py → Google Doc
                                  ↓
                    Slack DM → submitter + admin
```

## Brief Types

Five brief formats with distinct section structures, Q&A counts, tips tables, and formatting rules — all sourced from `brief_standards.py`:

| Type | Q&A | News | TOC | Reporter Section |
|---|---|---|---|---|
| Interview | 5–7 questions | Required | Yes | Reporter Information |
| Intro | 4–5 questions | Optional | No | Reporter Information |
| In-Person | 4–5 questions | Optional | No | Reporter Information |
| Broadcast | 7+ Q&A w/ answers | Required | Yes | About the Host |
| Podcast | None (Expected Topics) | Excluded | No | About the Host |

## Intelligence Sources

- **Glean** — internal knowledge graph (previous briefs, talking points, pitchbooks, FAQ docs)
- **Serper** — web search for recent news and reporter bylines
- **OG/JSON-LD scraping** — reporter headshots and social links from outlet pages
- **Wikipedia** — executive background as final fallback

## Stack

- **Agents**: [CrewAI](https://github.com/crewAIInc/crewAI) with sequential context chaining
- **LLM**: Gemini 2.5 Flash via Vertex AI (custom `GeminiLLM(BaseLLM)` class with 150s timeout)
- **Search**: Glean enterprise search API + Serper.dev
- **Output**: Google Drive API — HTML uploaded and converted to native Google Docs
- **Notifications**: Slack SDK — DMs to submitter, routed by email → user ID
- **Deployment**: Flask + Gunicorn on Railway

## Setup

```bash
cp .env.example .env
# Fill in your values (Glean, GCP, Slack, Drive)
pip install -r requirements.txt
python3 app.py
```

### Google Drive credentials

The pipeline writes to Drive using Application Default Credentials. For production deployment (Railway), base64-encode your service account JSON and set it as `DRIVE_ADC_BASE64`:

```bash
base64 -i ~/.config/gcloud/application_default_credentials.json | tr -d '\n'
```

### Validate configuration

```bash
python3 config.py        # prints all brief type rules
python3 brief_standards.py  # prints formatting spec
python3 qa_checker.py    # runs test suite (no API calls)
```

## Triggering a brief

Send a `POST /brief` with a JSON body:

```json
{
  "client_name": "Acme Corp",
  "exec_name": "Jane Smith",
  "reporter_url": "https://techcrunch.com/author/jane-reporter/",
  "brief_type": "Interview",
  "interview_date": "June 3, 2026",
  "interview_time": "10:00 AM ET",
  "virtual_or_inperson": "Virtual",
  "topic": "AI-driven product development",
  "on_record": "On Record",
  "staffed": "Yes",
  "submitter_email": "you@yourcompany.com"
}
```

Returns `202 Accepted` immediately. The Slack DM arrives when the brief is ready (~3–5 minutes).

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask webhook, fire-and-forget threading |
| `crew.py` | Pipeline orchestration, 5-agent context chain |
| `agents.py` | Agent definitions + `GeminiLLM` Vertex AI class |
| `tasks.py` | Task builders with structured JSON output specs |
| `data_gatherer.py` | Multi-source reporter + client intelligence gathering |
| `tools.py` | CrewAI `@tool` functions (scrape, Glean, Serper, Slack) |
| `brief_builder.py` | JSON → styled HTML → Google Doc |
| `qa_checker.py` | Deterministic schema validation (no LLM) |
| `brief_standards.py` | Single source of truth for all formatting rules |
| `config.py` | Env vars, `BriefRequest` dataclass, per-type rule lookup |

# LinkedIn Post Automation — Project Rules

## Standard Agent Repo Structure (ALL agents follow this)

```
agent-name/
├── app/                    # All application code lives here
│   ├── __init__.py
│   ├── config.py           # Config loader (env vars override YAML)
│   ├── notify.py           # Email notifications via Resend
│   ├── generator.py        # Core post drafting via Claude API
│   ├── topics.py           # Topic suggestion engine
│   └── voice/              # Sabeen's voice profile + sample posts
├── run.py                  # Entry point at project root
├── Procfile                # worker: python run.py
├── railway.toml            # nixpacks builder, startCommand
├── requirements.txt        # Flat pip dependencies (no pyproject.toml)
├── config.yaml             # Runtime config (env vars override)
├── .env.example            # Document all env vars
├── .gitignore
└── CLAUDE.md
```

## Deployment Rules — NEVER DEVIATE

- **Platform:** Railway (railway.app) with nixpacks builder
- **NO DOCKER. EVER.** No Dockerfile, no docker-compose, no container anything
- **NO pyproject.toml** — use requirements.txt only
- **NO src/ layout** — use app/ folder with run.py at root
- **Procfile:** `worker: python run.py`
- **railway.toml:** nixpacks builder with explicit startCommand
- **Env vars:** Set in Railway dashboard, override config.yaml via os.getenv()

## Email Notifications

- Use **Resend** (resend Python package)
- Env vars: RESEND_API_KEY, RESEND_FROM_EMAIL, RESEND_TO_EMAIL
- Skip silently if vars not set — never break the pipeline
- From address domain must be verified in Resend

## How to Run

```bash
# Suggest topics based on industry trends
python run.py suggest

# Generate drafts for a specific topic
python run.py generate --topic "Why most AI demos fail in production"

# Generate with a specific angle
python run.py generate --topic "AI hallucinations" --angle "When 'I don't know' is the right answer"

# Full pipeline: suggest + generate top 2 + email
python run.py full
```

## Voice Profile

Sabeen's voice profile lives in `app/voice/voice_profile.md`.
Sample posts (few-shot examples) live in `app/voice/sample_posts.md`.
These are loaded automatically by the generator — edit them to refine output quality.

## Posting Cadence

- 2x/week: Tuesday and Thursday
- Drafts are emailed via Resend for manual review and posting

## Topic Backlog

- `topics/suggested_topics.md` — add topics here manually or via `python run.py suggest`
- Format: one topic per line, optional angle after a dash

## Existing Agent Repos (for reference)

- `sabeenster/addy` — app/ + run.py + Procfile + railway.toml + Resend email
- `sabeenster/marketing-intel-agent` — app/ + run.py + templates/ + Resend email
- `sabeenster/replacement-tracker` — app/ + run.py + Procfile + railway.toml
- `sabeenster/david-analyst-agent` — same pattern

## Key Patterns

- Claude API for content generation (anthropic package)
- httpx for HTTP calls (not requests)
- Rich for console output formatting
- Results output to stdout/logs AND email

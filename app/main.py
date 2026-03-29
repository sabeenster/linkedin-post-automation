"""FastAPI web dashboard for LinkedIn Post Automation."""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import AppConfig

logger = logging.getLogger("linkedin.web")
config = AppConfig.load("config.yaml")
templates = Jinja2Templates(directory="templates")


async def scheduled_full_pipeline():
    """Run the full pipeline (suggest + generate + email) on schedule."""
    from app.generator import generate_drafts
    from app.notify import send_drafts_email, send_topics_email
    from app.topics import suggest_topics

    logger.info("Scheduled pipeline run starting...")
    try:
        topics = await suggest_topics(config)
        if topics:
            send_topics_email(topics, config)
            for t in topics[:2]:
                drafts = await generate_drafts(
                    t.get("topic", ""), config, angle=t.get("angle")
                )
                if drafts:
                    send_drafts_email(t.get("topic", ""), drafts, config)
        logger.info("Scheduled pipeline run complete")
    except Exception as e:
        logger.error(f"Scheduled pipeline failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    tz = os.getenv("SCHEDULE_TIMEZONE", "America/Los_Angeles")
    scheduler.add_job(
        scheduled_full_pipeline,
        CronTrigger(day_of_week="tue,thu", hour=8, minute=0, timezone=tz),
        id="full_pipeline",
        name="Tues/Thurs LinkedIn Pipeline",
    )
    scheduler.start()
    logger.info("Scheduler started: Tues/Thu 8am pipeline active (%s)", tz)
    yield
    scheduler.shutdown()


app = FastAPI(
    title="LinkedIn Post Automation",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Helpers ---

def _load_topics() -> list[dict]:
    """Parse topics/suggested_topics.md into structured data."""
    topics_path = config.topics_dir / "suggested_topics.md"
    if not topics_path.exists():
        return []
    content = topics_path.read_text()
    topics = []
    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("- "):
            continue
        # Parse "- **Topic** — Angle" or "- Topic — Angle"
        match = re.match(r"- \*\*(.+?)\*\*(?:\s*[—\-]\s*(.+))?", line)
        if match:
            topics.append({
                "topic": match.group(1),
                "angle": match.group(2) or "",
            })
        else:
            # Plain format: "- Topic — Angle"
            text = line[2:].strip()
            parts = re.split(r"\s*[—\-]\s*", text, maxsplit=1)
            topics.append({
                "topic": parts[0],
                "angle": parts[1] if len(parts) > 1 else "",
            })
    return topics


def _load_drafts() -> list[dict]:
    """Load draft files from drafts/ directory, most recent first."""
    drafts_dir = config.drafts_dir
    if not drafts_dir.exists():
        return []
    draft_files = sorted(drafts_dir.glob("*.md"), reverse=True)
    drafts = []
    for f in draft_files[:20]:
        drafts.append({
            "filename": f.name,
            "content": f.read_text(),
            "modified": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
        })
    return drafts


def _load_posted() -> list[dict]:
    """Load posted LinkedIn posts from posted/ directory, most recent first."""
    posted_dir = config.posted_dir
    if not posted_dir.exists():
        return []
    posted_files = sorted(posted_dir.glob("*.md"), reverse=True)
    posts = []
    for f in posted_files:
        content = f.read_text()
        # Parse frontmatter-style metadata
        meta = {}
        body = content
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().split("\n"):
                    if ": " in line:
                        key, val = line.split(": ", 1)
                        meta[key.strip()] = val.strip()
                body = parts[2].strip()
        posts.append({
            "filename": f.name,
            "topic": meta.get("topic", f.stem),
            "posted_date": meta.get("posted_date", ""),
            "content": body,
        })
    return posts


# --- Routes ---

@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    topics = _load_topics()
    drafts = _load_drafts()
    posted = _load_posted()
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "topics": topics,
            "drafts": drafts,
            "posted": posted,
        },
    )


@app.get("/api/topics")
async def get_topics():
    return {"topics": _load_topics()}


@app.post("/api/topics/add")
async def add_topic(topic: str = Form(...), angle: str = Form("")):
    topics_path = config.topics_dir / "suggested_topics.md"
    entry = f"\n- **{topic}**"
    if angle:
        entry += f" — {angle}"
    entry += "\n"
    with open(topics_path, "a") as f:
        f.write(entry)
    return JSONResponse({"status": "ok", "topic": topic})


@app.post("/api/topics/remove")
async def remove_topic(topic: str = Form(...)):
    topics_path = config.topics_dir / "suggested_topics.md"
    if not topics_path.exists():
        return JSONResponse({"status": "error", "message": "Topics file not found"}, status_code=404)
    lines = topics_path.read_text().splitlines(keepends=True)
    filtered = [line for line in lines if topic not in line]
    topics_path.write_text("".join(filtered))
    return JSONResponse({"status": "ok"})


@app.post("/api/generate")
async def generate(topic: str = Form(...), angle: str = Form("")):
    from app.generator import generate_drafts
    from app.notify import send_drafts_email

    drafts = await generate_drafts(topic, config, angle=angle or None)
    send_drafts_email(topic, drafts, config)
    return JSONResponse({"status": "ok", "topic": topic, "drafts": drafts})


@app.post("/api/finesse")
async def finesse(draft_text: str = Form(...), context: str = Form("")):
    from app.generator import finesse_draft
    from app.notify import send_drafts_email

    drafts = await finesse_draft(draft_text, config, context=context or None)
    send_drafts_email("Finessed Draft", drafts, config)
    return JSONResponse({"status": "ok", "drafts": drafts})


@app.post("/api/suggest")
async def suggest():
    from app.notify import send_topics_email
    from app.topics import suggest_topics

    topics = await suggest_topics(config)
    if topics:
        send_topics_email(topics, config)
    return JSONResponse({"status": "ok", "topics": topics})


@app.get("/api/drafts")
async def get_drafts():
    return {"drafts": _load_drafts()}


@app.get("/api/posted")
async def get_posted():
    return {"posted": _load_posted()}


@app.post("/api/posted/add")
async def mark_as_posted(
    topic: str = Form(...),
    content: str = Form(...),
    posted_date: str = Form(""),
):
    """Save a post as 'posted on LinkedIn'. Stores the final text for history and learning."""
    posted_dir = config.posted_dir
    posted_dir.mkdir(parents=True, exist_ok=True)

    if not posted_date:
        posted_date = datetime.now().strftime("%Y-%m-%d")

    # Create filename from date and topic
    slug = re.sub(r"[^\w\s-]", "", topic.lower())
    slug = re.sub(r"[\s_]+", "-", slug)[:40].strip("-")
    filename = f"{posted_date}_{slug}.md"

    file_content = f"""---
topic: {topic}
posted_date: {posted_date}
---

{content.strip()}
"""
    (posted_dir / filename).write_text(file_content)
    logger.info(f"Marked as posted: {filename}")

    # Also append to sample_posts.md so the generator learns from it
    _add_to_sample_posts(topic, content.strip())

    return JSONResponse({"status": "ok", "filename": filename})


def _add_to_sample_posts(topic: str, content: str):
    """Append a posted post to sample_posts.md for voice learning."""
    samples_path = config.voice_dir / "sample_posts.md"
    if not samples_path.exists():
        return

    existing = samples_path.read_text()
    # Find the highest post number
    numbers = re.findall(r"## Post (\d+)", existing)
    next_num = max(int(n) for n in numbers) + 1 if numbers else 1

    # Sanitize topic into a short title
    title = topic[:60]

    entry = f"\n\n---\n\n## Post {next_num}: {title}\n\n{content}\n"
    with open(samples_path, "a") as f:
        f.write(entry)

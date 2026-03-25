"""Topic suggestion engine — suggests LinkedIn topics based on industry trends."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import anthropic

from app.config import AppConfig

logger = logging.getLogger("linkedin.topics")

TOPIC_SYSTEM_PROMPT = """You are a content strategist for Sabeen Minns, CEO & Co-Founder of Agentway.
Agentway deploys custom AI intelligence for businesses — real operational AI, not demos.

Your job is to suggest LinkedIn post topics that:
1. Are timely and tied to real industry developments in AI & automation
2. Align with Sabeen's perspective: operational AI > hype, human value revealed by AI, real business outcomes
3. Have a contrarian or unexpected angle — not the obvious take
4. Would position Sabeen as a thought leader who builds, not just comments
5. Are grounded in real examples or observations, not abstract philosophizing

Sabeen's content pillars:
- AI agents in real business operations (not demos)
- Human value amplified (not replaced) by AI
- Bad automation and CX fails
- AI limitations, hallucinations, and knowing when to say "I don't know"
- The gap between shiny demos and operational reality
- The evolving role of builders and operators in an AI world

Return ONLY valid JSON — an array of objects with these fields:
- "topic": concise topic title (under 10 words)
- "angle": the specific take or hook (1-2 sentences)
- "why_timely": why post about this now (1 sentence)
"""


async def suggest_topics(config: AppConfig, count: int | None = None) -> list[dict]:
    """Suggest LinkedIn post topics based on industry trends.

    Returns a list of dicts with keys: topic, angle, why_timely.
    """
    n = count or config.topics.default_count

    client = anthropic.AsyncAnthropic()

    # Check if there are backlog topics to incorporate
    backlog = _load_backlog(config)
    backlog_context = ""
    if backlog:
        backlog_context = f"\n\nThe user already has these topics in their backlog (avoid duplicating these, but you can build on related themes):\n{backlog}"

    response = await client.messages.create(
        model=config.generation.model,
        max_tokens=2000,
        system=TOPIC_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Suggest {n} LinkedIn post topics for this week. Focus on: {config.topics.industry_focus}.{backlog_context}\n\nReturn only the JSON array.",
            },
        ],
    )

    raw = response.content[0].text.strip()

    # Extract JSON from response (handle markdown code blocks)
    if "```" in raw:
        json_match = raw.split("```")[1]
        if json_match.startswith("json"):
            json_match = json_match[4:]
        raw = json_match.strip()

    try:
        topics = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse topic suggestions: {raw[:200]}")
        return []

    # Append to suggested_topics.md
    _save_suggestions(config, topics)

    return topics


def _load_backlog(config: AppConfig) -> str:
    """Load existing topic backlog."""
    backlog_path = config.topics_dir / "suggested_topics.md"
    if not backlog_path.exists():
        return ""
    content = backlog_path.read_text()
    # Strip out the header/comments, return just topic lines
    lines = [
        line.strip()
        for line in content.split("\n")
        if line.strip() and not line.strip().startswith("#") and not line.strip().startswith("<!--")
        and not line.strip().startswith("-->")
    ]
    return "\n".join(lines)


def _save_suggestions(config: AppConfig, topics: list[dict]) -> None:
    """Append suggested topics to the backlog file."""
    config.topics_dir.mkdir(parents=True, exist_ok=True)
    backlog_path = config.topics_dir / "suggested_topics.md"

    date_str = datetime.now().strftime("%Y-%m-%d")
    new_section = f"\n\n## Suggestions — {date_str}\n\n"
    for t in topics:
        topic = t.get("topic", "")
        angle = t.get("angle", "")
        why = t.get("why_timely", "")
        new_section += f"- **{topic}** — {angle}\n  _Why now: {why}_\n"

    with open(backlog_path, "a") as f:
        f.write(new_section)

    logger.info(f"Appended {len(topics)} topic suggestions to {backlog_path}")

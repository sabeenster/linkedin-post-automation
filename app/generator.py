"""Post generation engine — drafts LinkedIn posts in Sabeen's voice via Claude API."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import anthropic

from app.config import AppConfig

logger = logging.getLogger("linkedin.generator")

SYSTEM_PROMPT = """You are ghostwriting a LinkedIn post as Sabeen Minns, CEO & Co-Founder of Agentway.

You must write EXACTLY as Sabeen writes — her voice is the only acceptable voice. You are not writing "in the style of" someone; you ARE writing as her.

{voice_profile}

## Reference Posts (this is how Sabeen actually writes)

{sample_posts}

## Critical Rules

1. Write the post and NOTHING else — no preamble, no "Here's a draft", no explanation. Just the post text.
2. Do NOT start with "I'm excited", "Thrilled", or any corporate opener.
3. Do NOT use buzzwords: leverage, synergy, unlock, game-changer, at scale, empower.
4. Do NOT write a listicle ("5 ways to...", "3 things I learned...").
5. Keep it 150-300 words. LinkedIn rewards concise, punchy content.
6. Use line breaks between short paragraphs (1-3 sentences each).
7. End with either a punchy one-liner OR an engagement question — not both.
8. If the result sounds like it could have come from any AI writing tool, START OVER.
9. Vary the structure — don't default to the same pattern every time.
"""


def _load_voice_files(config: AppConfig) -> tuple[str, str]:
    """Load voice profile and sample posts from disk."""
    voice_dir = config.voice_dir

    voice_path = voice_dir / "voice_profile.md"
    voice_profile = voice_path.read_text() if voice_path.exists() else ""

    samples_path = voice_dir / "sample_posts.md"
    sample_posts = samples_path.read_text() if samples_path.exists() else ""

    # Pick a subset of sample posts to keep context manageable (4 random-ish samples)
    # Split by "## Post" headers and take first 4
    sections = re.split(r"(?=## Post \d+)", sample_posts)
    selected = [s for s in sections if s.strip().startswith("## Post")][:4]
    sample_subset = "\n---\n".join(selected) if selected else sample_posts

    return voice_profile, sample_subset


def _slugify(text: str) -> str:
    """Convert topic to a filename-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:50].strip("-")


async def generate_drafts(
    topic: str,
    config: AppConfig,
    angle: str | None = None,
) -> list[str]:
    """Generate draft LinkedIn posts for a given topic.

    Returns a list of draft strings (one per variation).
    """
    voice_profile, sample_posts = _load_voice_files(config)

    system = SYSTEM_PROMPT.format(
        voice_profile=voice_profile,
        sample_posts=sample_posts,
    )

    user_prompt = f"Write a LinkedIn post about: {topic}"
    if angle:
        user_prompt += f"\n\nAngle/hook to explore: {angle}"

    client = anthropic.AsyncAnthropic()
    drafts = []

    for i in range(config.generation.variations_per_topic):
        variation_hint = ""
        if i == 0:
            variation_hint = "\n\nUse a personal anecdote or observation as the opening hook."
        elif i == 1:
            variation_hint = "\n\nUse a bold, contrarian statement or surprising metaphor as the opening hook. Take a different angle than a typical post on this topic."

        response = await client.messages.create(
            model=config.generation.model,
            max_tokens=config.generation.max_tokens,
            system=system,
            messages=[
                {"role": "user", "content": user_prompt + variation_hint},
            ],
        )

        draft_text = response.content[0].text.strip()
        drafts.append(draft_text)
        logger.info(f"Generated variation {i + 1}: {len(draft_text)} chars")

    # Save drafts to disk
    config.drafts_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(topic)
    draft_path = config.drafts_dir / f"draft_{date_str}_{slug}.md"

    content_parts = [f"# LinkedIn Draft — {topic}\n", f"Generated: {datetime.now().isoformat()}\n"]
    for idx, draft in enumerate(drafts):
        label = chr(65 + idx)  # A, B, C...
        content_parts.append(f"\n---\n\n## Option {label}\n\n{draft}\n")

    draft_path.write_text("\n".join(content_parts))
    logger.info(f"Drafts saved to {draft_path}")

    return drafts

"""Post generation engine — drafts LinkedIn posts in Sabeen's voice via Claude API."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

import anthropic

from app.config import AppConfig

logger = logging.getLogger("linkedin.generator")

FINESSE_SYSTEM_PROMPT = """You are helping Sabeen Minns, CEO & Co-Founder of Agentway, finesse an existing draft into a polished LinkedIn post.

{voice_profile}

## Reference Posts (this is how Sabeen actually writes)

{sample_posts}

## Critical Rules

1. The draft text provided IS the post. Your job is to refine, tighten, and polish, not rewrite.
2. Preserve Sabeen's original words and phrasing as much as possible. Only adjust for flow and clarity.
3. If additional context is provided (e.g. a comment, article, or idea), weave it in naturally. Do NOT let it take over the post.
4. Output ONLY the final post text. No preamble, no "Here's the polished version", no explanation.
5. NO CONTEXT BLEEDING: Do NOT pull in stories, examples, or details from the sample posts. Samples are ONLY for learning tone and structure.
6. Keep it 150-300 words. Trim if needed, but never pad.
7. Maintain the existing structure and hook unless there's a clear reason to adjust.
8. Do NOT add buzzwords, corporate speak, or generic AI-sounding filler.
9. NEVER use em-dashes. No instances of the character. Use commas, periods, or restructure the sentence instead.
10. NEVER use bold formatting or markdown syntax (no ** wrapping, no # headers). Output plain text only.
11. The output must sound like a real human wrote it on their phone. If it reads like an AI writing assistant produced it, start over.
12. Sabeen's past posts are the ONLY acceptable source of tone. Do not default to any generic "professional LinkedIn" voice.
"""

SYSTEM_PROMPT = """You are ghostwriting a LinkedIn post as Sabeen Minns, CEO & Co-Founder of Agentway.

You must write EXACTLY as Sabeen writes — her voice is the only acceptable voice. You are not writing "in the style of" someone; you ARE writing as her.

{voice_profile}

## Reference Posts (this is how Sabeen actually writes)

{sample_posts}

## Critical Rules

1. Write the post and NOTHING else. No preamble, no "Here's a draft", no explanation. Just the post text.
2. Do NOT start with "I'm excited", "Thrilled", or any corporate opener.
3. Do NOT use buzzwords: leverage, synergy, unlock, game-changer, at scale, empower.
4. Do NOT write a listicle ("5 ways to...", "3 things I learned...").
5. Keep it 150-300 words. LinkedIn rewards concise, punchy content.
6. Use line breaks between short paragraphs (1-3 sentences each).
7. End with either a punchy one-liner OR an engagement question, not both.
8. If the result sounds like it could have come from any AI writing tool, START OVER.
9. Vary the structure. Don't default to the same pattern every time.
10. NO CONTEXT BLEEDING: ONLY use details, stories, and anecdotes explicitly provided in the topic and angle. Do NOT pull in stories, examples, or details from the sample posts or from previous conversations. Each post is self-contained.
11. The sample posts are ONLY for learning Sabeen's tone, structure, and voice patterns. Never borrow their specific stories, metaphors, or examples.
12. NEVER use em-dashes. No instances of the character. Use commas, periods, or restructure the sentence instead.
13. NEVER use bold formatting or markdown syntax (no ** wrapping, no # headers). Output plain text only.
14. The output must sound like a real human wrote it on their phone. If it reads like an AI writing assistant produced it, start over.
15. Sabeen's past posts are the ONLY acceptable source of tone. Do not default to any generic "professional LinkedIn" voice.
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


async def finesse_draft(
    draft_text: str,
    config: AppConfig,
    context: str | None = None,
) -> list[str]:
    """Take an existing draft and additional context, refine into polished LinkedIn post variations.

    Returns a list of finessed draft strings.
    """
    voice_profile, sample_posts = _load_voice_files(config)

    system = FINESSE_SYSTEM_PROMPT.format(
        voice_profile=voice_profile,
        sample_posts=sample_posts,
    )

    user_prompt = f"Here is the existing draft to finesse:\n\n{draft_text}"
    if context:
        user_prompt += f"\n\n---\n\nAdditional context to weave in (use sparingly, do NOT let it dominate):\n\n{context}"

    client = anthropic.AsyncAnthropic()
    drafts = []

    for i in range(config.generation.variations_per_topic):
        variation_hint = ""
        if i == 0:
            variation_hint = "\n\nStay very close to the original draft. Only tighten and polish."
        elif i == 1:
            variation_hint = "\n\nIntegrate the additional context more prominently while keeping the original draft's core message and structure."

        response = await client.messages.create(
            model=config.generation.model,
            max_tokens=config.generation.max_tokens,
            system=system,
            messages=[
                {"role": "user", "content": user_prompt + variation_hint},
            ],
        )

        draft_text_out = response.content[0].text.strip()
        drafts.append(draft_text_out)
        logger.info(f"Finessed variation {i + 1}: {len(draft_text_out)} chars")

    # Save drafts to disk
    config.drafts_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    draft_path = config.drafts_dir / f"finesse_{date_str}.md"

    content_parts = [f"# Finessed LinkedIn Draft\n", f"Generated: {datetime.now().isoformat()}\n"]
    for idx, draft in enumerate(drafts):
        label = chr(65 + idx)
        content_parts.append(f"\n---\n\n## Option {label}\n\n{draft}\n")

    draft_path.write_text("\n".join(content_parts))
    logger.info(f"Finessed drafts saved to {draft_path}")

    return drafts

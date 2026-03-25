"""Configuration loader for LinkedIn Post Automation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class GenerationConfig:
    model: str = "claude-sonnet-4-20250514"
    variations_per_topic: int = 2
    max_tokens: int = 1500


@dataclass
class PostingConfig:
    cadence: str = "2x/week"
    days: list[str] = field(default_factory=lambda: ["Tuesday", "Thursday"])


@dataclass
class TopicsConfig:
    default_count: int = 5
    industry_focus: str = "AI & automation, enterprise AI adoption, operational intelligence, human-AI collaboration"


@dataclass
class AppConfig:
    posting: PostingConfig = field(default_factory=PostingConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    topics: TopicsConfig = field(default_factory=TopicsConfig)

    @property
    def anthropic_api_key(self) -> str:
        return os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def resend_api_key(self) -> str:
        return os.getenv("RESEND_API_KEY", "")

    @property
    def resend_from_email(self) -> str:
        return os.getenv("RESEND_FROM_EMAIL", "")

    @property
    def resend_to_email(self) -> list[str]:
        raw = os.getenv("RESEND_TO_EMAIL", "")
        return [e.strip() for e in raw.split(",") if e.strip()]

    @property
    def voice_dir(self) -> Path:
        return Path(__file__).parent / "voice"

    @property
    def drafts_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "drafts"

    @property
    def topics_dir(self) -> Path:
        return Path(__file__).resolve().parent.parent / "topics"

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "AppConfig":
        """Load config from YAML file, falling back to defaults."""
        path = Path(path)
        if not path.exists():
            return cls()

        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        config = cls()

        p_raw = raw.get("posting", {})
        config.posting = PostingConfig(
            cadence=p_raw.get("cadence", "2x/week"),
            days=p_raw.get("days", ["Tuesday", "Thursday"]),
        )

        g_raw = raw.get("generation", {})
        config.generation = GenerationConfig(
            model=g_raw.get("model", "claude-sonnet-4-20250514"),
            variations_per_topic=g_raw.get("variations_per_topic", 2),
            max_tokens=g_raw.get("max_tokens", 1500),
        )

        t_raw = raw.get("topics", {})
        config.topics = TopicsConfig(
            default_count=t_raw.get("default_count", 5),
            industry_focus=t_raw.get("industry_focus", config.topics.industry_focus),
        )

        return config

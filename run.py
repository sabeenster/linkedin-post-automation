"""LinkedIn Post Automation — Entry point."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.config import AppConfig

console = Console()
logging.basicConfig(
    level=logging.WARNING,
    format="%(message)s",
    handlers=[RichHandler(console=console, show_time=False, show_path=False)],
)
logging.getLogger("linkedin").setLevel(logging.INFO)
logger = logging.getLogger("linkedin")


async def run_suggest(config: AppConfig):
    """Suggest LinkedIn post topics based on industry trends."""
    from app.notify import send_topics_email
    from app.topics import suggest_topics

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning industry trends for topic ideas...", total=None)
        topics = await suggest_topics(config)
        progress.update(task, description=f"Found {len(topics)} topic suggestions")
        progress.remove_task(task)

    if not topics:
        console.print("[yellow]No topics generated. Check your API key.[/yellow]")
        return

    console.print()
    console.print(Panel.fit("[bold blue]Topic Suggestions[/bold blue]"))
    for t in topics:
        console.print(f"  [bold]{t.get('topic', '')}[/bold]")
        console.print(f"    {t.get('angle', '')}")
        console.print(f"    [dim]{t.get('why_timely', '')}[/dim]")
        console.print()

    send_topics_email(topics, config)


async def run_generate(config: AppConfig, topic: str, angle: str | None = None):
    """Generate draft LinkedIn posts for a topic."""
    from app.generator import generate_drafts
    from app.notify import send_drafts_email

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Drafting posts about: {topic}...", total=None)
        drafts = await generate_drafts(topic, config, angle=angle)
        progress.update(task, description=f"Generated {len(drafts)} draft variations")
        progress.remove_task(task)

    if not drafts:
        console.print("[yellow]No drafts generated. Check your API key.[/yellow]")
        return

    console.print()
    for idx, draft in enumerate(drafts):
        label = chr(65 + idx)
        console.print(Panel(
            Markdown(draft),
            title=f"Option {label}",
            border_style="blue",
            width=80,
        ))
        console.print()

    send_drafts_email(topic, drafts, config)


async def run_finesse(config: AppConfig, draft_file: str, context_file: str | None = None):
    """Finesse an existing draft with optional additional context."""
    from app.generator import finesse_draft
    from app.notify import send_drafts_email

    draft_path = Path(draft_file)
    if not draft_path.exists():
        console.print(f"[red]Draft file not found: {draft_file}[/red]")
        return

    draft_text = draft_path.read_text().strip()

    context = None
    if context_file:
        ctx_path = Path(context_file)
        if ctx_path.exists():
            context = ctx_path.read_text().strip()
        else:
            console.print(f"[yellow]Context file not found: {context_file} — proceeding without it[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Finessing draft...", total=None)
        drafts = await finesse_draft(draft_text, config, context=context)
        progress.update(task, description=f"Finessed {len(drafts)} variations")
        progress.remove_task(task)

    if not drafts:
        console.print("[yellow]No drafts generated.[/yellow]")
        return

    console.print()
    for idx, draft in enumerate(drafts):
        label = chr(65 + idx)
        console.print(Panel(
            Markdown(draft),
            title=f"Option {label}",
            border_style="green",
            width=80,
        ))
        console.print()

    send_drafts_email("Finessed Draft", drafts, config)


async def run_full(config: AppConfig):
    """Full pipeline: suggest topics, pick top 2, generate drafts, email everything."""
    from app.generator import generate_drafts
    from app.notify import send_drafts_email, send_topics_email
    from app.topics import suggest_topics

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Step 1: Suggest topics
        task = progress.add_task("Scanning trends for topic ideas...", total=None)
        topics = await suggest_topics(config)
        progress.update(task, description=f"Found {len(topics)} topics")
        progress.remove_task(task)

    if not topics:
        console.print("[yellow]No topics generated.[/yellow]")
        return

    console.print(Panel.fit("[bold blue]Topic Suggestions[/bold blue]"))
    for t in topics:
        console.print(f"  [bold]{t.get('topic', '')}[/bold] — {t.get('angle', '')}")
    console.print()

    send_topics_email(topics, config)

    # Step 2: Generate drafts for top 2 topics
    top_topics = topics[:2]
    for t in top_topics:
        topic_title = t.get("topic", "")
        topic_angle = t.get("angle", "")
        console.print(f"\n[bold]Generating drafts for:[/bold] {topic_title}")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Drafting: {topic_title}...", total=None)
            drafts = await generate_drafts(topic_title, config, angle=topic_angle)
            progress.update(task, description=f"Generated {len(drafts)} variations")
            progress.remove_task(task)

        if drafts:
            for idx, draft in enumerate(drafts):
                label = chr(65 + idx)
                console.print(Panel(
                    Markdown(draft),
                    title=f"Option {label}",
                    border_style="blue",
                    width=80,
                ))

            send_drafts_email(topic_title, drafts, config)

    console.print()
    console.print(Panel.fit("[bold green]Pipeline complete![/bold green]"))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LinkedIn Post Automation")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # suggest
    subparsers.add_parser("suggest", help="Suggest topics based on industry trends")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate draft posts for a topic")
    gen_parser.add_argument("--topic", "-t", required=True, help="Topic to write about")
    gen_parser.add_argument("--angle", "-a", help="Optional angle or hook")

    # finesse
    fin_parser = subparsers.add_parser("finesse", help="Finesse an existing draft with optional context")
    fin_parser.add_argument("--draft", "-d", required=True, help="Path to draft text file")
    fin_parser.add_argument("--context", "-c", help="Path to additional context file (article, comment, etc.)")

    # full
    subparsers.add_parser("full", help="Full pipeline: suggest + generate + email")

    args = parser.parse_args()
    config = AppConfig.load("config.yaml")

    if not config.anthropic_api_key:
        logger.error("No ANTHROPIC_API_KEY set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    console.print(Panel.fit(
        "[bold blue]LinkedIn Post Automation[/bold blue]",
        subtitle="Powered by Agentway",
    ))

    if args.command == "suggest":
        asyncio.run(run_suggest(config))
    elif args.command == "generate":
        asyncio.run(run_generate(config, args.topic, args.angle))
    elif args.command == "finesse":
        asyncio.run(run_finesse(config, args.draft, args.context))
    elif args.command == "full":
        asyncio.run(run_full(config))
    else:
        parser.print_help()

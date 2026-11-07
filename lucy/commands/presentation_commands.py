"""
Presentation commands — /presentation, /slides, /ppt.

Allows users to create executive 16:9 widescreen PowerPoint presentations,
browse modern themes, and inspect slide layout templates directly from the terminal.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lucy.core.commands import Command, CommandResult

logger = logging.getLogger(__name__)


class PresentationCommand(Command):
    """Slash command to generate professional presentation decks."""

    @property
    def name(self) -> str:
        return "presentation"

    @property
    def aliases(self) -> list[str]:
        return ["slides", "ppt"]

    @property
    def description(self) -> str:
        return "Create modern 16:9 widescreen PowerPoint presentations (.pptx)"

    @property
    def usage(self) -> str:
        return "/presentation [create <topic>|themes|templates|help] [--theme <name>] [--out <file>]"

    async def execute(self, args: str, state: Any) -> CommandResult:
        from lucy.services.presentation_generator import (
            THEMES,
            SlideDeck,
            generate_presentation_from_spec,
        )

        args = (args or "").strip()
        parts = args.split()
        action = parts[0].lower() if parts else "help"

        # ── 1. Help ──
        if action in ("help", "--help", "-h") or not args:
            theme_list = ", ".join(THEMES.keys())
            help_text = (
                "Presentation Design Engine (/presentation, /slides, /ppt)\n"
                "────────────────────────────────────────────────────────────\n"
                "Generate executive-grade, 16:9 widescreen PowerPoint decks.\n\n"
                "Commands:\n"
                "  /presentation create <topic>     Generate an end-to-end presentation deck\n"
                "  /presentation themes             List available color themes and aesthetics\n"
                "  /presentation templates          Inspect available slide layout types\n\n"
                "Options:\n"
                "  --theme <name>                   Choose palette (modern_dark, clean_light, executive_navy, warm_editorial, vibrant_tech)\n"
                "  --out <filename.pptx>            Specify output file path (default: <topic>.pptx)\n\n"
                f"Available Themes: {theme_list}\n"
            )
            return CommandResult(output=help_text)

        # ── 2. List Themes ──
        if action in ("themes", "theme", "list-themes"):
            lines = [
                "Available Presentation Design Themes",
                "────────────────────────────────────────────────────────────",
            ]
            theme_descriptions = {
                "modern_dark": "Obsidian/slate dark background (#0F172A) with vibrant indigo/cyan accents. Best for tech, engineering, and developers.",
                "clean_light": "Crisp white background (#FFFFFF) with slate cards and royal blue accents. Best for business, operations, and enterprise.",
                "executive_navy": "Deep royal navy background (#0A192F) with champagne gold/amber accents. Best for investor pitches and leadership decks.",
                "warm_editorial": "Warm alabaster sand background (#FDFBF7) with terracotta accents. Best for research, philosophy, and editorial briefs.",
                "vibrant_tech": "Cyber dark background (#090D16) with vivid violet and teal accents. Best for AI, next-gen products, and launches.",
            }
            for name, theme in THEMES.items():
                desc = theme_descriptions.get(name, "Curated aesthetic theme")
                lines.append(f"• {name}")
                lines.append(f"  {desc}")
                lines.append(f"  Fonts: {theme.font_title} / {theme.font_body}")
                lines.append("")
            return CommandResult(output="\n".join(lines).strip())

        # ── 3. Templates / Archetypes ──
        if action in ("templates", "template", "layouts"):
            lines = [
                "Slide Layout Templates & Archetypes (16:9 Widescreen)",
                "────────────────────────────────────────────────────────────",
                "1. Title / Hero Slide",
                "   High-impact presentation cover with category pill, title, subtitle, and metadata footer.",
                "",
                "2. Multi-Column Feature Cards (2, 3, or 4 columns)",
                "   Distinct cards with accent borders, category badges, bold headers, and concise bullets.",
                "",
                "3. Key Metrics & KPIs",
                "   Giant numbers (44pt+) with bold labels and contextual metric benchmarks.",
                "",
                "4. Process & Workflow Pipeline",
                "   Horizontal sequential steps (01 -> 02 -> 03 -> 04) with step numbers and descriptions.",
                "",
                "5. Side-by-Side Comparison",
                "   Contrasting dual-column layout (e.g. Current vs Target, Problem vs Solution).",
                "",
                "6. Vision & Editorial Quote",
                "   Large stylized quotation with speaker name and organization role.",
                "",
                "7. Summary & Next Steps",
                "   Two-column split: Key Takeaways with checkmarks on left, Action Roadmap on right.",
            ]
            return CommandResult(output="\n".join(lines))

        # ── 4. Create Presentation ──
        if action == "create":
            rest_tokens = parts[1:]
            theme = "modern_dark"
            out_file = None

            # Parse optional flags
            topic_tokens = []
            idx = 0
            while idx < len(rest_tokens):
                token = rest_tokens[idx]
                if token == "--theme" and idx + 1 < len(rest_tokens):
                    theme = rest_tokens[idx + 1]
                    idx += 2
                elif token == "--out" and idx + 1 < len(rest_tokens):
                    out_file = rest_tokens[idx + 1]
                    idx += 2
                else:
                    topic_tokens.append(token)
                    idx += 1

            topic = " ".join(topic_tokens).strip() or "Project Overview"

            if not out_file:
                safe_name = "".join(c if c.isalnum() else "_" for c in topic.lower())
                safe_name = "_".join(filter(None, safe_name.split("_")))[:30] or "presentation"
                out_file = f"{safe_name}.pptx"

            # Build a comprehensive presentation tailored to the topic
            deck = SlideDeck(theme=theme)
            deck.add_title_slide(
                title=topic.title(),
                subtitle="Strategic Overview & Architecture",
                presenter="LucyCode Autonomous System",
                date="November 2026",
                tag="EXECUTIVE BRIEFING",
            )
            deck.add_card_slide(
                title=f"Core Pillars of {topic.title()}",
                subtitle="Fundamental building blocks and architectural components",
                tag="ARCHITECTURE",
                cards=[
                    {
                        "title": "Foundational Design",
                        "badge": "PILLAR 1",
                        "body": [
                            "Modular system architecture",
                            "High-availability operational design",
                            "Strict security & isolation guardrails",
                        ],
                    },
                    {
                        "title": "Autonomous Execution",
                        "badge": "PILLAR 2",
                        "body": [
                            "Automated workflow loops",
                            "Sub-second tool execution",
                            "Resilient failure recovery",
                        ],
                    },
                    {
                        "title": "Continuous Verification",
                        "badge": "PILLAR 3",
                        "body": [
                            "Comprehensive test coverage",
                            "Automated benchmark tracking",
                            "Deterministic self-evaluation",
                        ],
                    },
                ],
            )
            deck.add_metrics_slide(
                title="Performance & Impact",
                subtitle="Measured benchmarks and operational efficiency",
                tag="KEY METRICS",
                metrics=[
                    {"value": "10x", "label": "Execution Velocity", "detail": "Accelerated turnaround"},
                    {"value": "99.9%", "label": "Reliability SLA", "detail": "Zero-downtime execution"},
                    {"value": "<50ms", "label": "Latency", "detail": "Real-time response time"},
                ],
            )
            deck.add_process_slide(
                title="Execution Roadmap",
                subtitle="End-to-end phased implementation pipeline",
                tag="ROADMAP",
                steps=[
                    {"step": "01", "title": "Discover", "description": "Audit system requirements and establish benchmarks"},
                    {"step": "02", "title": "Implement", "description": "Construct core pipelines with high-rigor unit testing"},
                    {"step": "03", "title": "Verify", "description": "Run continuous validation loops and stress benchmarks"},
                    {"step": "04", "title": "Deploy", "description": "Roll out to production with automated telemetry"},
                ],
            )
            deck.add_summary_slide(
                title="Summary & Next Steps",
                subtitle="Path forward for project rollout",
                tag="SUMMARY",
                takeaways=[
                    f"Complete architectural blueprint established for {topic.title()}",
                    "High-rigor quality and benchmark verification completed",
                    "Ready for production scaling and stakeholder review",
                ],
                next_steps=[
                    "Distribute presentation deck to project stakeholders",
                    "Execute Phase 1 deployment milestones",
                    "Establish live telemetry and continuous monitoring",
                ],
            )

            try:
                saved_path = deck.save(out_file)
                p = Path(saved_path)
                size_kb = round(p.stat().st_size / 1024, 1) if p.exists() else 0.0

                out_msg = (
                    f"Successfully generated presentation deck!\n"
                    f"• Topic: {topic.title()}\n"
                    f"• Theme: {theme}\n"
                    f"• Output File: {saved_path} ({size_kb} KB)\n"
                    f"• Slides: 5 widescreen (16:9) slides\n\n"
                    f"Open file with: open '{saved_path}'"
                )
                return CommandResult(output=out_msg)
            except Exception as e:
                return CommandResult(error=f"Failed to generate presentation: {e}")

        return CommandResult(
            error=f"Unknown presentation action: '{action}'\nUsage: {self.usage}"
        )


def get_commands() -> list[Command]:
    """Return all presentation command instances."""
    return [PresentationCommand()]

"""
Presentation Design & Generation Tool for LucyCode.

Empowers the agent to generate modern, executive-grade PowerPoint presentations (.pptx)
with curated themes, structured cards, KPI metrics, timelines, and comparison layouts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lucy.core.tool import Tool, ToolContext, ToolResult


class PresentationTool(Tool):
    """Tool for generating professional 16:9 widescreen PowerPoint presentations."""

    @property
    def name(self) -> str:
        return "presentation"

    @property
    def description(self) -> str:
        return (
            "Generate modern, executive-grade 16:9 widescreen PowerPoint presentations (.pptx) "
            "with curated design themes (modern_dark, clean_light, executive_navy, warm_editorial, vibrant_tech), "
            "multi-column feature cards, big-number KPI metrics, process workflows, and comparison slides."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "template", "list_themes"],
                    "description": "Action to perform: 'create' to build deck, 'template' for starter schema, 'list_themes' to inspect palettes.",
                    "default": "create",
                },
                "theme": {
                    "type": "string",
                    "enum": ["modern_dark", "clean_light", "executive_navy", "warm_editorial", "vibrant_tech"],
                    "description": "Design aesthetic theme for the deck (default: modern_dark).",
                    "default": "modern_dark",
                },
                "title": {
                    "type": "string",
                    "description": "Main deck title (e.g. 'Autonomous AI Agent Architecture').",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output path for the .pptx file (default: './presentation.pptx').",
                    "default": "presentation.pptx",
                },
                "slides": {
                    "type": "array",
                    "description": "List of slide specifications (types: 'title', 'cards', 'metrics', 'process', 'comparison', 'quote', 'summary').",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["title", "cards", "metrics", "process", "comparison", "quote", "summary"],
                            },
                            "title": {"type": "string"},
                            "subtitle": {"type": "string"},
                            "tag": {"type": "string"},
                            "cards": {"type": "array", "items": {"type": "object"}},
                            "metrics": {"type": "array", "items": {"type": "object"}},
                            "steps": {"type": "array", "items": {"type": "object"}},
                            "left": {"type": "object"},
                            "right": {"type": "object"},
                            "quote": {"type": "string"},
                            "author": {"type": "string"},
                            "role": {"type": "string"},
                            "takeaways": {"type": "array", "items": {"type": "string"}},
                            "next_steps": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
        }

    def is_read_only(self, tool_input: dict[str, Any]) -> bool:
        action = tool_input.get("action", "create")
        return action in ["template", "list_themes"]

    def get_prompt(self) -> str:
        return (
            "Generate visually compelling, modern 16:9 widescreen PowerPoint presentations (.pptx) "
            "with structured cards, metrics, and curated color palettes."
        )

    async def call(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        from lucy.services.presentation_generator import (
            THEMES,
            generate_presentation_from_spec,
        )

        action = tool_input.get("action", "create")

        # ── 1. List Themes ──
        if action == "list_themes":
            themes_info = {}
            for name, theme in THEMES.items():
                themes_info[name] = {
                    "font_title": theme.font_title,
                    "font_body": theme.font_body,
                    "bg_rgb": theme.bg_color,
                    "accent_rgb": theme.accent,
                }
            return ToolResult(
                data=json.dumps(
                    {
                        "available_themes": list(THEMES.keys()),
                        "default_theme": "modern_dark",
                        "details": themes_info,
                    },
                    indent=2,
                )
            )

        # ── 2. Template / Starter Schema ──
        if action == "template":
            sample_spec = {
                "theme": "modern_dark",
                "output_path": "presentation.pptx",
                "slides": [
                    {
                        "type": "title",
                        "title": "Presentation Title",
                        "subtitle": "Subtitle describing the key thesis",
                        "presenter": "Presenter Name",
                        "date": "2026",
                        "tag": "OVERVIEW",
                    },
                    {
                        "type": "cards",
                        "title": "Core Pillars",
                        "subtitle": "High-level feature architecture",
                        "tag": "ARCHITECTURE",
                        "cards": [
                            {"title": "Pillar 1", "badge": "TIER 1", "body": ["Point A", "Point B"]},
                            {"title": "Pillar 2", "badge": "TIER 2", "body": ["Point C", "Point D"]},
                            {"title": "Pillar 3", "badge": "TIER 3", "body": ["Point E", "Point F"]},
                        ],
                    },
                    {
                        "type": "metrics",
                        "title": "Key Performance Indicators",
                        "tag": "METRICS",
                        "metrics": [
                            {"value": "99.9%", "label": "Uptime", "detail": "High availability SLA"},
                            {"value": "10x", "label": "Speed", "detail": "End-to-end task throughput"},
                        ],
                    },
                    {
                        "type": "summary",
                        "title": "Summary & Next Steps",
                        "takeaways": ["Production ready", "Zero dependencies"],
                        "next_steps": ["Deploy to production", "Review metrics"],
                    },
                ],
            }
            return ToolResult(data=json.dumps(sample_spec, indent=2))

        # ── 3. Create Presentation ──
        slides = tool_input.get("slides", [])
        title = tool_input.get("title", "")
        theme = tool_input.get("theme", "modern_dark")
        output_path = tool_input.get("output_path", "presentation.pptx")

        if not slides and title:
            # Generate a starter default deck for this title
            slides = [
                {
                    "type": "title",
                    "title": title,
                    "subtitle": "Generated by LucyCode Autonomous Workstation",
                    "tag": "PRESENTATION",
                },
                {
                    "type": "cards",
                    "title": "Overview",
                    "cards": [
                        {"title": "Objective", "badge": "GOAL", "body": [f"Deliver comprehensive {title} overview"]},
                        {"title": "Approach", "badge": "METHOD", "body": ["Modular architecture", "Automated verification"]},
                    ],
                },
                {
                    "type": "summary",
                    "title": "Summary",
                    "takeaways": [f"Successfully outlined {title}"],
                    "next_steps": ["Review presentation slides", "Iterate content if required"],
                },
            ]

        if not slides:
            return ToolResult(
                error="Cannot create presentation without 'slides' or 'title'."
            )

        spec = {
            "theme": theme,
            "output_path": output_path,
            "slides": slides,
        }

        try:
            saved_file = generate_presentation_from_spec(spec)
            p = Path(saved_file)
            size_kb = round(p.stat().st_size / 1024, 1) if p.exists() else 0.0

            return ToolResult(
                data=(
                    f"Successfully created presentation:\n"
                    f"- File: {saved_file} ({size_kb} KB)\n"
                    f"- Theme: {theme}\n"
                    f"- Total Slides: {len(slides)}\n"
                    f"- Slide Types: {', '.join(s.get('type', 'cards') for s in slides)}"
                )
            )
        except Exception as e:
            return ToolResult(error=f"Failed to create presentation: {e}")


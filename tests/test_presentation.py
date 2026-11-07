"""
Unit tests for Presentation Design Service, Tool, and Slash Command.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pptx
from lucy.commands.presentation_commands import PresentationCommand, get_commands
from lucy.core.commands import find_command
from lucy.core.skills_engine import get_skills_engine
from lucy.core.tool import ToolContext
from lucy.services.presentation_generator import (
    THEMES,
    SlideDeck,
    generate_presentation_from_spec,
)
from lucy.tools.presentation_tools import PresentationTool


class TestPresentation(unittest.TestCase):
    """Test suite for Presentation Generator, Tool, and Slash Commands."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_theme_palettes(self):
        """Test that all 5 curated themes are defined with valid RGB tuples."""
        expected_themes = [
            "modern_dark",
            "clean_light",
            "executive_navy",
            "warm_editorial",
            "vibrant_tech",
        ]
        for name in expected_themes:
            self.assertIn(name, THEMES)
            theme = THEMES[name]
            self.assertEqual(len(theme.bg_color), 3)
            self.assertEqual(len(theme.card_bg), 3)
            self.assertEqual(len(theme.accent), 3)
            self.assertTrue(theme.font_title)
            self.assertTrue(theme.font_body)

    def test_slide_deck_widescreen_and_slide_types(self):
        """Test SlideDeck builds all 7 slide types with 16:9 widescreen dimensions."""
        out_path = Path(self.temp_dir) / "test_deck.pptx"

        deck = SlideDeck(theme="modern_dark")
        # 1. Title Slide
        deck.add_title_slide(
            title="Next-Gen AI Systems",
            subtitle="Autonomous Desktop & Workstation Control",
            presenter="Lucy Engineering",
            date="2026-11-07",
            tag="ARCHITECTURE",
        )
        # 2. Card Slide
        deck.add_card_slide(
            title="Three Core Pillars",
            subtitle="Architectural breakdown",
            cards=[
                {"title": "Pillar 1", "badge": "CORE", "body": ["Point A", "Point B"]},
                {"title": "Pillar 2", "badge": "DESKTOP", "body": "Direct automation"},
                {"title": "Pillar 3", "badge": "HARNESS", "body": ["Self-healing loop"]},
            ],
            tag="PILLARS",
        )
        # 3. Metrics Slide
        deck.add_metrics_slide(
            title="Key Performance Indicators",
            metrics=[
                {"value": "99.9%", "label": "Uptime", "detail": "Zero downtime"},
                {"value": "10x", "label": "Efficiency", "detail": "Throughput gain"},
            ],
            tag="METRICS",
        )
        # 4. Process Slide
        deck.add_process_slide(
            title="Deployment Pipeline",
            steps=[
                {"step": "01", "title": "Build", "description": "Compile modules"},
                {"step": "02", "title": "Test", "description": "Run unit suites"},
                {"step": "03", "title": "Ship", "description": "Push to production"},
            ],
            tag="PIPELINE",
        )
        # 5. Comparison Slide
        deck.add_comparison_slide(
            title="Legacy vs Modern",
            left_column={"title": "Legacy", "subtitle": "Manual", "items": ["Slow", "Fragile"]},
            right_column={"title": "LucyCode", "subtitle": "Autonomous", "items": ["Fast", "Self-healing"]},
            tag="COMPARISON",
        )
        # 6. Quote Slide
        deck.add_quote_slide(
            quote="Autonomous agents represent the future of software construction.",
            author="Lucy Team",
            role="Systems Engineering",
            tag="VISION",
        )
        # 7. Summary Slide
        deck.add_summary_slide(
            title="Summary & Next Steps",
            takeaways=["Production ready", "Zero regressions"],
            next_steps=["Deploy widely", "Monitor telemetry"],
            tag="ROADMAP",
        )

        saved = deck.save(out_path)
        self.assertTrue(Path(saved).exists())
        self.assertGreater(Path(saved).stat().st_size, 1000)

        # Inspect generated PPTX using python-pptx
        prs = pptx.Presentation(saved)
        self.assertEqual(len(prs.slides), 7)
        # Verify 16:9 widescreen dimensions (13.333 inches x 7.5 inches)
        width_in = prs.slide_width.inches
        height_in = prs.slide_height.inches
        self.assertAlmostEqual(width_in, 13.333, places=2)
        self.assertAlmostEqual(height_in, 7.5, places=2)

    def test_generate_from_spec(self):
        """Test generating presentation deck from declarative dictionary spec."""
        out_path = Path(self.temp_dir) / "spec_deck.pptx"
        spec = {
            "theme": "clean_light",
            "output_path": str(out_path),
            "slides": [
                {
                    "type": "title",
                    "title": "Clean Light Deck",
                    "subtitle": "Declarative Spec Test",
                },
                {
                    "type": "cards",
                    "title": "Cards Section",
                    "cards": [
                        {"title": "Card 1", "body": ["Item 1", "Item 2"]},
                    ],
                },
                {
                    "type": "summary",
                    "title": "Wrap Up",
                    "takeaways": ["Success"],
                    "next_steps": ["Done"],
                },
            ],
        }
        res_file = generate_presentation_from_spec(spec)
        self.assertTrue(Path(res_file).exists())
        prs = pptx.Presentation(res_file)
        self.assertEqual(len(prs.slides), 3)

    def test_presentation_tool(self):
        """Test PresentationTool invocation for create, template, and list_themes."""
        tool = PresentationTool()
        self.assertEqual(tool.name, "presentation")

        async def run_tool_tests():
            ctx = ToolContext(cwd=self.temp_dir)

            # 1. list_themes
            res_themes = await tool.call({"action": "list_themes"}, ctx)
            self.assertIn("available_themes", res_themes.data)
            self.assertIn("modern_dark", res_themes.data)

            # 2. template
            res_tmpl = await tool.call({"action": "template"}, ctx)
            self.assertIn("slides", res_tmpl.data)

            # 3. create with title only (generates starter deck)
            out_file = Path(self.temp_dir) / "starter.pptx"
            res_create = await tool.call(
                {"action": "create", "title": "Automated Workstation", "output_path": str(out_file)},
                ctx,
            )
            self.assertIn("Successfully created presentation", res_create.data)
            self.assertTrue(out_file.exists())

            # 4. error when neither title nor slides provided
            res_err = await tool.call({"action": "create"}, ctx)
            self.assertTrue(res_err.is_error)

        asyncio.run(run_tool_tests())

    def test_presentation_command(self):
        """Test /presentation slash command and aliases."""
        cmd = find_command("presentation")
        self.assertIsNotNone(cmd)
        self.assertIn("slides", cmd.aliases)
        self.assertIn("ppt", cmd.aliases)

        async def run_cmd_tests():
            # Help
            h_res = await cmd.execute("help", None)
            self.assertIn("Presentation Design Engine", h_res.output)

            # Themes
            t_res = await cmd.execute("themes", None)
            self.assertIn("executive_navy", t_res.output)

            # Templates
            tmpl_res = await cmd.execute("templates", None)
            self.assertIn("Multi-Column Feature Cards", tmpl_res.output)

            # Create
            out_ppt = Path(self.temp_dir) / "cmd_created.pptx"
            c_res = await cmd.execute(
                f"create AI Engineering --theme executive_navy --out {out_ppt}",
                None,
            )
            self.assertIn("Successfully generated presentation deck", c_res.output)
            self.assertTrue(out_ppt.exists())

        asyncio.run(run_cmd_tests())

    def test_skills_engine_discovery(self):
        """Test that presentation-design is discovered and auto-activates on keywords."""
        engine = get_skills_engine()
        skills = engine.discover(force_refresh=True)
        names = [s.metadata.name for s in skills]
        self.assertIn("presentation-design", names)

        # Check activation on presentation keywords
        active = engine.activate_for_context(
            cwd=os.getcwd(),
            user_prompt="Can you create a ppt presentation with modern slides?",
        )
        active_names = [s.metadata.name for s in active]
        self.assertIn("presentation-design", active_names)


if __name__ == "__main__":
    unittest.main()

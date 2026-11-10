"""
Unit tests for the Pixel Art Dog Companion and slash commands.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lucy.commands.companion_commands import CompanionCommand, get_commands
from lucy.core.commands import find_command
from lucy.tui.companion import DogCompanion, render_sprite_lines, SPRITES, PALETTE


class TestDogCompanion(unittest.TestCase):
    """Test suite for DogCompanion rendering, state transitions, and slash commands."""

    def test_palette_and_sprites(self):
        """Verify palette colors and sprite dimensions."""
        self.assertIn(" ", PALETTE)
        self.assertIn("#", PALETTE)
        self.assertIn("G", PALETTE)
        self.assertIn("E", PALETTE)
        self.assertIn("W", PALETTE)
        self.assertIn("B", PALETTE)

        for name, rows in SPRITES.items():
            self.assertEqual(len(rows), 24, f"Sprite {name} must have 24 rows")
            for r in rows:
                self.assertEqual(len(r), 24, f"Sprite {name} rows must have 24 columns")

    def test_render_sprite_lines(self):
        """Verify half-block rendering produces 12 terminal rows."""
        lines = render_sprite_lines("idle_1")
        self.assertEqual(len(lines), 12)
        # Verify ANSI escape sequences are present
        self.assertTrue(any("\033[38;2;" in l for l in lines))

    def test_companion_actions_and_state(self):
        """Test pet, feed, bark, and sleep actions."""
        dog = DogCompanion(name="Lucy")

        # 1. Initial State
        self.assertEqual(dog.state.happiness, 100)
        self.assertEqual(dog.state.energy, 100)
        self.assertEqual(dog.state.mood, "idle")
        self.assertEqual(dog.state.name, "Lucy")

        # 2. Pet
        pet_msg = dog.pet()
        self.assertTrue(pet_msg)
        self.assertEqual(dog.state.mood, "happy")
        self.assertIn("happy", dog.get_current_sprite())

        # 3. Feed Treat
        treat_msg = dog.feed()
        self.assertTrue(treat_msg)
        self.assertEqual(dog.state.treats, 4)
        self.assertEqual(dog.state.mood, "treat")

        # 4. Bark / Advice
        bark_msg = dog.bark()
        self.assertTrue(bark_msg)
        self.assertEqual(dog.state.mood, "bark")

        # 5. Sleep / Wake
        sleep_msg = dog.toggle_sleep()
        self.assertTrue(dog.state.is_sleeping)
        self.assertEqual(dog.state.mood, "sleep")
        self.assertIn("sleep", dog.get_current_sprite())

        wake_msg = dog.toggle_sleep()
        self.assertFalse(dog.state.is_sleeping)

    def test_render_tui(self):
        """Verify render_tui returns formatted terminal string with stats."""
        dog = DogCompanion(name="Lucy")
        output = dog.render_tui()
        self.assertIn("Lucy", output)
        self.assertIn("Happiness", output)
        self.assertIn("Energy", output)
        self.assertIn("Controls:", output)

    def test_companion_slash_command(self):
        """Verify /companion, /pet, /dog slash commands."""
        cmd = find_command("companion")
        self.assertIsNotNone(cmd)
        self.assertIn("pet", cmd.aliases)
        self.assertIn("dog", cmd.aliases)

        async def _run_cmd_tests():
            # 1. Default render
            res_default = await cmd.execute("", None)
            self.assertIn("Lucy", res_default.output)

            # 2. /companion pet
            res_pet = await cmd.execute("pet", None)
            self.assertIn("Lucy", res_pet.output)

            # 3. /companion feed
            res_feed = await cmd.execute("feed", None)
            self.assertIn("Treats Given", res_feed.output)

            # 4. /companion bark
            res_bark = await cmd.execute("bark", None)
            self.assertIn("Lucy", res_bark.output)

            # 5. /companion say Hello Dev
            res_say = await cmd.execute("say Hello Dev", None)
            self.assertIn("Hello Dev", res_say.output)

        asyncio.run(_run_cmd_tests())


if __name__ == "__main__":
    unittest.main()


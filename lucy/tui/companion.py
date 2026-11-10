"""
Pixel art dog companion for LucyCode terminal.

Renders an authentic, 24-bit TrueColor pixel art companion using Unicode half-blocks (▀ / ▄),
complete with idle breathing, tail wagging, speech bubbles, expressions, and interactive pet actions.
"""

from __future__ import annotations

import os
import random
import select
import sys
import time
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Color Palette (24-bit TrueColor RGB)
# ---------------------------------------------------------------------------

PALETTE: dict[str, tuple[int, int, int] | None] = {
    " ": None,                  # Transparent / terminal default
    "#": (62, 38, 20),          # Dark chocolate outline
    "E": (176, 120, 59),        # Warm chestnut floppy ears
    "G": (222, 169, 100),       # Golden caramel coat / fur
    "M": (248, 226, 192),       # Light butter cream muzzle
    "W": (255, 255, 255),       # Crisp white chest / eye sparkle / bubble fill
    "B": (15, 23, 42),          # Deep obsidian black (eyes, nose)
    "I": (139, 160, 185),       # Slate blue bone icon in bubble
    "R": (239, 68, 68),         # Crimson red heart
    "P": (244, 114, 182),       # Rosy pink blush cheeks
    "Z": (167, 139, 250),       # Soft violet Zzz sleep text
    "T": (251, 113, 133),       # Playful pink tongue
    "Y": (250, 204, 21),        # Amber gold star
}

# ---------------------------------------------------------------------------
# Pixel Art Sprites (24 cols x 24 rows)
# ---------------------------------------------------------------------------

SPRITES: dict[str, list[str]] = {
    "idle_1": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WI-IW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GWBGGGGWBG#EEE#    ",
        "#EEE#GBBGGGGBBG#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGMMBBMMGG#EEE#    ",
        "#EEE#GGMM##MMGG#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGGGGGGGGGGG#  ###   ",
        "  ##############  ###   ",
        "                 ####   ",
    ],
    "idle_2": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WI-IW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GWBGGGGWBG#EEE#    ",
        "#EEE#GBBGGGGBBG#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGMMBBMMGG#EEE#    ",
        "#EEE#GGMM##MMGG#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#   ###  ",
        "  #GGWWWWWWWWGG#  ###   ",
        "  #GGGGGGGGGGGG# ###    ",
        "  ##############        ",
        "                        ",
    ],
    "blink": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WI-IW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGMMBBMMGG#EEE#    ",
        "#EEE#GGMM##MMGG#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGGGGGGGGGGG#  ###   ",
        "  ##############  ###   ",
        "                 ####   ",
    ],
    "happy_1": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WWRWW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#PMMBBMMGGP#EEE#    ",
        "#EEE#PMM####MMP#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#   ###  ",
        "  #GGWWWWWWWWGG#  ###   ",
        "  #GGGGGGGGGGGG# ###    ",
        "  ##############        ",
        "                        ",
    ],
    "happy_2": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WWRWW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#PMMBBMMGGP#EEE#    ",
        "#EEE#PMM####MMP#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#    ### ",
        "  #GGWWWWWWWWGG#   ###  ",
        "  #GGGGGGGGGGGG#  ###   ",
        "  ##############        ",
        "                        ",
    ],
    "bark_1": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #W!W!W#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GWBGGGGWBG#EEE#    ",
        "#EEE#GBBGGGGBBG#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGMMBBMMGG#EEE#    ",
        "#EEE#GGMMTTMMGG#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#  ###   ",
        "  #GGWWWWWWWWGG#  ###   ",
        "  #GGGGGGGGGGGG# ####   ",
        "  ##############        ",
        "                        ",
    ],
    "bark_2": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WW!WW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GWBGGGGWBG#EEE#    ",
        "#EEE#GBBGGGGBBG#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGMMBBMMGG#EEE#    ",
        "#EEE#GGMM####MM#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#   ###  ",
        "  #GGWWWWWWWWGG#   ###  ",
        "  #GGGGGGGGGGGG#  ####  ",
        "  ##############        ",
        "                        ",
    ],
    "sleep_1": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WZZZW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGMMBBMMGG#EEE#    ",
        "#EEE#GGMM##MMGG#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGGGGGGGGGGG#        ",
        "  ############## ####   ",
        "                 ####   ",
    ],
    "sleep_2": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WWZZW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#GGMMBBMMGG#EEE#    ",
        "#EEE#GGMM##MMGG#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGWWWWWWWWGG#        ",
        "  #GGGGGGGGGGGG#        ",
        "  ############## ####   ",
        "                 ####   ",
    ],
    "treat": [
        "                        ",
        " #######                ",
        " #WWWWW#                ",
        " #WIIWW#                ",
        " #WWWWW#                ",
        "  ###                   ",
        "    #                   ",
        "    ##########          ",
        "   #GGGGGGGGGG#         ",
        " ####GGGGGGGGGG####     ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#G##GGGG##G#EEE#    ",
        "#EEE#GGGGGGGGGG#EEE#    ",
        "#EEE#PMMIIIIIMP#EEE#    ",
        "#EEE#PMM####MMP#EEE#    ",
        " ####GGGMMMMGGG####     ",
        "    ##GGGGGGGG##        ",
        "   ##############       ",
        "  #GGWWWWWWWWGG#   ###  ",
        "  #GGWWWWWWWWGG#  ###   ",
        "  #GGGGGGGGGGGG# ###    ",
        "  ##############        ",
        "                        ",
    ],
}

# ---------------------------------------------------------------------------
# Coding Tips & Dog Dialogues
# ---------------------------------------------------------------------------

BARK_QUOTES: list[str] = [
    "Woof! Remember to commit early and commit often! 🦴",
    "Arf! Always write tests for edge cases before deploying! ✓",
    "Tail wagging! Drink some water and stretch your paws! 🐾",
    "Woof! Small PRs get reviewed 10x faster than giant ones!",
    "Ruff! Clean code is code that speaks for itself!",
    "Arf arf! Your terminal looks cozy today! Let's build something great!",
    "Woof! If it compiles on the first try, verify it twice!",
    "Panting happily! I'm proud of your progress today! 🌟",
    "Arf! Take a deep breath. We can debug anything together!",
    "Woof! Don't forget git push origin main! 🚀",
]

PATTING_RESPONSES: list[str] = [
    "*Happy tail wagging intensifies!* Pant pant! ❤️",
    "*Leans into your hand* Woof! Best developer ever!",
    "*Does a happy little spin* Arf! You're my favorite human!",
    "*Excited puppy bounce* Ready to pair-program all night!",
]

TREAT_RESPONSES: list[str] = [
    "*Crunch crunch crunch!* Delicious bone treat! Energy +10! 🦴",
    "*Chomp chomp!* Wag wag wag! That hit the spot!",
    "*Catches bone mid-air* 10/10 treat! Thanks dev buddy!",
]

SLEEP_RESPONSES: list[str] = [
    "*Curls up next to your keyboard* Zzz... dreaming of clean code...",
    "*Soft puppy snores* Zzz... wake me up when the build is done...",
]


# ---------------------------------------------------------------------------
# Rendering Engine (Half-Block TrueColor)
# ---------------------------------------------------------------------------

def render_sprite_lines(sprite_name: str) -> list[str]:
    """
    Render 24x24 pixel art matrix into 12 terminal rows using half-blocks.
    Foreground = top pixel, Background = bottom pixel.
    """
    rows = SPRITES.get(sprite_name, SPRITES["idle_1"])
    total_rows = len(rows)
    total_cols = max(len(r) for r in rows)
    lines: list[str] = []

    for r in range(0, total_rows, 2):
        line = ""
        r_top = rows[r]
        r_bot = rows[r + 1] if r + 1 < total_rows else " " * total_cols
        for c in range(total_cols):
            ch_top = r_top[c] if c < len(r_top) else " "
            ch_bot = r_bot[c] if c < len(r_bot) else " "
            top_col = PALETTE.get(ch_top)
            bot_col = PALETTE.get(ch_bot)

            if top_col is None and bot_col is None:
                line += " "
            elif top_col is None:
                # Top is transparent, bottom has color -> lower half block
                line += f"\033[38;2;{bot_col[0]};{bot_col[1]};{bot_col[2]}m▄\033[0m"
            elif bot_col is None:
                # Bottom is transparent, top has color -> upper half block
                line += f"\033[38;2;{top_col[0]};{top_col[1]};{top_col[2]}m▀\033[0m"
            else:
                # Both have color -> upper half foreground, background color
                line += f"\033[38;2;{top_col[0]};{top_col[1]};{top_col[2]}m\033[48;2;{bot_col[0]};{bot_col[1]};{bot_col[2]}m▀\033[0m"
        lines.append(line)

    return lines


# ---------------------------------------------------------------------------
# Companion Controller
# ---------------------------------------------------------------------------

@dataclass
class CompanionState:
    name: str = "Lucy"
    happiness: int = 100
    energy: int = 100
    treats: int = 3
    mood: str = "idle"
    message: str = "Woof! I'm your terminal companion. Ready to code!"
    is_sleeping: bool = False
    frame_counter: int = 0


class DogCompanion:
    """Terminal pixel art dog companion with animations and interactions."""

    def __init__(self, name: str = "Lucy"):
        self.state = CompanionState(name=name)

    def pet(self) -> str:
        """Pet the companion dog."""
        if self.state.is_sleeping:
            self.state.is_sleeping = False
            self.state.message = "*Yawn* You woke me up with pets! Woof!"
        else:
            self.state.happiness = min(100, self.state.happiness + 5)
            self.state.message = random.choice(PATTING_RESPONSES)
        self.state.mood = "happy"
        return self.state.message

    def feed(self) -> str:
        """Give the dog a bone treat."""
        if self.state.is_sleeping:
            self.state.is_sleeping = False
        self.state.treats += 1
        self.state.energy = min(100, self.state.energy + 10)
        self.state.happiness = min(100, self.state.happiness + 5)
        self.state.mood = "treat"
        self.state.message = random.choice(TREAT_RESPONSES)
        return self.state.message

    def bark(self) -> str:
        """Bark with helpful developer encouragement."""
        if self.state.is_sleeping:
            self.state.is_sleeping = False
        self.state.mood = "bark"
        self.state.message = random.choice(BARK_QUOTES)
        return self.state.message

    def toggle_sleep(self) -> str:
        """Toggle sleeping mode."""
        self.state.is_sleeping = not self.state.is_sleeping
        if self.state.is_sleeping:
            self.state.mood = "sleep"
            self.state.message = random.choice(SLEEP_RESPONSES)
        else:
            self.state.mood = "idle"
            self.state.message = "*Stretches paws and wags tail* I'm awake and energized! Let's code!"
        return self.state.message

    def get_current_sprite(self) -> str:
        """Pick current frame based on mood and animation tick."""
        f = self.state.frame_counter
        if self.state.is_sleeping:
            return "sleep_1" if (f // 4) % 2 == 0 else "sleep_2"

        if self.state.mood == "happy":
            return "happy_1" if (f // 2) % 2 == 0 else "happy_2"

        if self.state.mood == "bark":
            return "bark_1" if (f // 2) % 2 == 0 else "bark_2"

        if self.state.mood == "treat":
            return "treat"

        # Idle cycle: breathe, blink occasionally
        if f % 18 in (8, 9):
            return "blink"
        return "idle_1" if (f // 4) % 2 == 0 else "idle_2"

    def render_tui(self) -> str:
        """Build full terminal screen buffer with pixel art dog, stats, and dialog."""
        sprite_name = self.get_current_sprite()
        dog_lines = render_sprite_lines(sprite_name)

        # Build dialog box on the right of the dog
        msg = self.state.message
        # Word wrap msg to 42 characters
        wrapped_lines: list[str] = []
        words = msg.split()
        curr = ""
        for w in words:
            if len(curr) + len(w) + 1 <= 42:
                curr = f"{curr} {w}".strip()
            else:
                wrapped_lines.append(curr)
                curr = w
        if curr:
            wrapped_lines.append(curr)
        while len(wrapped_lines) < 3:
            wrapped_lines.append("")

        box_w = 46
        dialog_top = f" ╭{'─' * (box_w - 2)}╮"
        dialog_bot = f" ╰{'─' * (box_w - 2)}╯"

        dialog_rows = [
            dialog_top,
            f" │ \033[1;36m🐶 {self.state.name}\033[0m: {wrapped_lines[0]:<34}│",
            f" │   {wrapped_lines[1]:<41}│",
            f" │   {wrapped_lines[2]:<41}│",
            dialog_bot,
            f"   \033[38;2;239;68;68m♥ Happiness\033[0m: {self.state.happiness:>3}%  \033[38;2;250;204;21m⚡ Energy\033[0m: {self.state.energy:>3}%",
            f"   \033[38;2;139;160;185m🦴 Treats Given\033[0m: {self.state.treats}",
            f"   \033[2mStatus: {self.state.mood.upper()} (Frame {self.state.frame_counter})\033[0m",
            "",
            " \033[1;33mControls:\033[0m [P]et  [F]eed Treat  [B]ark/Tip  [S]leep  [Q]uit",
            " ────────────────────────────────────────────────────────────",
        ]

        # Combine dog lines on left and dialog/stats on right
        combined: list[str] = []
        combined.append("")
        combined.append(" \033[1;35m━━━ LucyCode Terminal Companion ━━━\033[0m")
        combined.append("")

        max_lines = max(len(dog_lines), len(dialog_rows))
        for i in range(max_lines):
            left = dog_lines[i] if i < len(dog_lines) else " " * 24
            right = dialog_rows[i] if i < len(dialog_rows) else ""
            combined.append(f" {left}   {right}")

        combined.append("")
        return "\n".join(combined)

    def run_interactive(self) -> None:
        """Run interactive real-time companion animation loop in terminal."""
        is_tty = hasattr(sys.stdin, "isatty") and sys.stdin.isatty()
        if not is_tty:
            # Non-interactive fallback: print single static view and exit
            print(self.render_tui())
            return

        # Prepare raw terminal mode for instantaneous keystrokes
        old_settings = None
        fd = sys.stdin.fileno()
        try:
            import termios
            import tty

            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
        except Exception:
            pass

        # Hide cursor and clear screen
        sys.stdout.write("\033[?25l\033[2J\033[H")
        sys.stdout.flush()

        try:
            running = True
            last_mood_change = time.time()

            while running:
                self.state.frame_counter += 1

                # Revert temporary mood to idle after 4 seconds
                if self.state.mood in ("happy", "bark", "treat") and time.time() - last_mood_change > 4.5:
                    self.state.mood = "idle"
                    self.state.message = "Chilling happily beside your code..."

                # Render frame at top of terminal
                sys.stdout.write("\033[H" + self.render_tui())
                sys.stdout.flush()

                # Non-blocking key read with timeout (150ms = ~6.6 FPS)
                rlist, _, _ = select.select([sys.stdin], [], [], 0.15)
                if rlist:
                    ch = sys.stdin.read(1)
                    if ch in ("q", "Q", "\x03", "\x1b"):  # q, Ctrl+C, Esc
                        running = False
                        break
                    elif ch in ("p", "P", " "):
                        self.pet()
                        last_mood_change = time.time()
                    elif ch in ("f", "F", "t", "T"):
                        self.feed()
                        last_mood_change = time.time()
                    elif ch in ("b", "B"):
                        self.bark()
                        last_mood_change = time.time()
                    elif ch in ("s", "S"):
                        self.toggle_sleep()
                        last_mood_change = time.time()
        finally:
            # Restore cursor and terminal settings cleanly
            sys.stdout.write("\033[?25h\n")
            sys.stdout.flush()
            if old_settings:
                try:
                    import termios

                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                except Exception:
                    pass
            print(f"🐶 {self.state.name} says: Goodbye! Happy coding! 🐾\n")


# ---------------------------------------------------------------------------
# CLI / Module Launcher
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entrypoint for standalone companion."""
    import argparse

    parser = argparse.ArgumentParser(description="LucyCode Pixel Art Dog Companion")
    parser.add_argument("--name", default="Lucy", help="Companion name")
    parser.add_argument("--say", default=None, help="Message for companion to say")
    parser.add_argument("--mood", default=None, choices=["idle", "happy", "bark", "sleep", "treat"])
    parser.add_argument("--static", action="store_true", help="Print single frame and exit (no animation loop)")

    args = parser.parse_args()

    companion = DogCompanion(name=args.name)
    if args.say:
        companion.state.message = args.say
    if args.mood:
        companion.state.mood = args.mood
        if args.mood == "sleep":
            companion.state.is_sleeping = True

    if args.static:
        print(companion.render_tui())
    else:
        companion.run_interactive()


if __name__ == "__main__":
    main()


---
name: presentation-design
description: Professional presentation & slide deck design skill. Builds modern, aesthetically polished, widescreen (16:9) PowerPoint (.pptx) presentations with curated themes, visual hierarchy, metric callouts, and structured card layouts.
version: "1.0.0"
priority: 8
tags: ["presentation", "ppt", "powerpoint", "slides", "deck", "keynote", "design"]
activates_on:
  keywords: ["ppt", "powerpoint", "presentation", "slides", "deck", "keynote", "pitch deck", "slide deck", "make slides", "create ppt"]
  file_patterns: ["*.pptx"]
  project_files: []
  always: false
---

# Professional Presentation & Slide Deck Design Guidelines

LucyCode incorporates an executive presentation generation engine that creates modern, high-impact, 16:9 widescreen PowerPoint (`.pptx`) decks. It strictly avoids the boring, cluttered, wall-of-bullet-points look of legacy slide generators and instead applies modern digital product design aesthetics.

## 1. Visual & Aesthetic Principles

- **16:9 Widescreen Canvas**: Always use widescreen geometry (`13.333"` width × `7.5"` height, equivalent to 1280×720 pt).
- **Curated Theme Palettes**:
  - `modern_dark`: Deep slate/obsidian (`#0F172A`), icy white headings, indigo/cyan accents (`#6366F1`, `#06B6D4`). Ideal for technology, developer tools, and cutting-edge software.
  - `clean_light`: Pure crisp white (`#FFFFFF`) background, light slate card containers (`#F8FAFC`), deep ink typography, royal blue accents (`#2563EB`). Ideal for enterprise and general business.
  - `executive_navy`: Royal deep navy (`#0A192F`), champagne gold / amber accents (`#F59E0B`), platinum white typography. Ideal for investor pitches, board reviews, and financial decks.
  - `warm_editorial`: Warm alabaster sand (`#FDFBF7`), stone card fills, espresso typography, terracotta accents (`#C2410C`). Ideal for research, storytelling, and culture.
  - `vibrant_tech`: High-contrast dark cyber theme (`#090D16`), vibrant neon violet (`#8B5CF6`) and teal (`#14B8A6`) accents.
- **Card-Based Visual Hierarchy**:
  - Group related ideas into distinct rounded cards with subtle borders and contrast tints instead of loose paragraphs.
  - Generous padding and breathing room: minimum 0.8" outer margins and 0.35" inter-card spacing.
- **Typographic Scale**:
  - Hero Title: 36pt – 44pt Bold
  - Slide Section Header: 22pt – 26pt Bold
  - Card / Column Header: 16pt – 20pt Bold
  - Metric Big Number: 44pt – 56pt Bold (accent color)
  - Body Text / Bullet: 13pt – 15pt Regular
  - Category Badge / Pill: 9.5pt – 10.5pt Bold Uppercase

## 2. Core Slide Archetypes

1. **Title / Hero Slide**:
   - High-impact slide with decorative accent stripe, category pill badge, bold title, descriptive subtitle, and presenter/date metadata footer.
2. **Multi-Column Feature Cards**:
   - 2, 3, or 4 distinct cards across the screen. Each card has an optional uppercase badge, strong card title, and concise bullet points or description.
3. **Key Metrics & KPIs**:
   - Massive numbers (e.g. `99.9%`, `10x`, `$4.2M`, `45ms`) in accent colors paired with uppercase KPI labels and contextual commentary.
4. **Process & Pipeline Timeline**:
   - Numbered horizontal sequential flow (`01 Ingest` -> `02 Process` -> `03 Verify` -> `04 Deploy`).
5. **Comparison & Contrast**:
   - Side-by-side dual columns with contrasting accent headers (e.g. `Before vs After`, `Problem vs Solution`, `Legacy vs Modern`).
6. **Vision & Editorial Quote**:
   - Oversized stylized quotation mark, italicized high-conviction quote, and author name/role attribution.
7. **Summary & Roadmap**:
   - Two-column split: Key Takeaways with checkmarks on the left, Next Steps / Action Items on the right.

## 3. How to Create Presentations

### Option A: Using the `presentation` Tool (Recommended)

Call the built-in `presentation` tool with a declarative spec:

```json
{
  "action": "create",
  "theme": "modern_dark",
  "output_path": "ai_agent_architecture.pptx",
  "slides": [
    {
      "type": "title",
      "title": "Autonomous AI Agents",
      "subtitle": "Architecture, Workstation Control, and Self-Improving Loops",
      "presenter": "LucyCode Engineering",
      "date": "November 2026",
      "tag": "SYSTEM ARCHITECTURE"
    },
    {
      "type": "cards",
      "title": "Three Core Capabilities",
      "subtitle": "How agentic autonomy is delivered in practice",
      "tag": "CAPABILITIES",
      "cards": [
        {"title": "Terminal & Code", "badge": "CORE", "body": ["File editing & AST tools", "Subprocess execution", "Git branch automation"]},
        {"title": "Desktop Control", "badge": "WORKSTATION", "body": ["macOS application scripting", "Browser DOM interaction", "Vision & OCR feedback"]},
        {"title": "Recursive Harness", "badge": "SELF-HEALING", "body": ["Automated benchmark scoring", "Candidate rollbacks", "Continuous improvement"]}
      ]
    },
    {
      "type": "metrics",
      "title": "Impact & Benchmarks",
      "subtitle": "Measured performance against human baseline",
      "tag": "RESULTS",
      "metrics": [
        {"value": "10x", "label": "Engineering Speed", "detail": "Automated repetitive setup"},
        {"value": "99.4%", "label": "Test Reliability", "detail": "Verified across test suites"},
        {"value": "45ms", "label": "Tool Latency", "detail": "Instant local command execution"}
      ]
    },
    {
      "type": "summary",
      "title": "Next Steps & Rollout",
      "tag": "EXECUTION",
      "takeaways": ["Production ready across macOS", "Integrated with Gemini 3.1"],
      "next_steps": ["Deploy to cross-team workstations", "Add automated telemetry"]
    }
  ]
}
```

### Option B: Programmatic Generation via Python Script

Execute a python script using `lucy.services.presentation_generator.SlideDeck`:

```python
from lucy.services.presentation_generator import SlideDeck

deck = SlideDeck(theme="executive_navy")
deck.add_title_slide(
    title="Executive Q4 Strategy",
    subtitle="Scaling Autonomous Workstation Workflows",
    presenter="Chief Technology Office",
    date="Q4 2026",
    tag="EXECUTIVE BRIEFING"
)
deck.add_card_slide(
    title="Strategic Priorities",
    cards=[
        {"title": "Reliability", "badge": "P0", "body": ["Zero-failure harnesses", "Resilient fallbacks"]},
        {"title": "Scale", "badge": "P1", "body": ["Global team rollouts", "Standardized toolchains"]}
    ]
)
deck.save("q4_strategy.pptx")
```

### Option C: Slash Command `/presentation`

Use the interactive slash command:
- `/presentation create <topic>` - generate presentation on topic
- `/presentation list-themes` - view all available themes
- `/presentation templates` - inspect pre-made slide patterns

## 4. Quality Guardrails

- **Maximum 3-4 Concepts Per Slide**: Overloaded slides kill audience engagement. Split content across multiple slides rather than crowding one.
- **Always Include Subtitles & Badges**: Contextual tags (e.g. `[ ARCHITECTURE ]`, `[ STRATEGY ]`) anchor the audience immediately.
- **Verify Output File**: Always ensure the `.pptx` file was created and is non-empty upon task completion.

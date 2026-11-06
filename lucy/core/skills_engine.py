"""
Skills Engine — declarative, context-aware capability system.

Skills are markdown files (SKILL.md) with YAML frontmatter that provide:
- Specialized instructions for specific tasks
- Domain expertise (debugging, security, performance, etc.)
- Framework-specific knowledge (React, Django, FastAPI, etc.)
- Custom workflows and checklists

Skills can be:
- Built-in (shipped with Lucy)
- User-defined (~/.lucycode/skills/)
- Workspace-specific (.lucy/skills/ or .lucycode/skills/)
- Installed from registries / plugins

Skills are auto-activated based on context:
- Project type detection (package.json -> Node.js skills)
- File patterns (*.tsx -> React skill)
- User request analysis (mentions "debug" -> debugging skill)
- Explicit activation via /skill command
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

from lucy.core.config import CONFIG_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SkillActivation:
    """When this skill should auto-activate."""
    # File patterns that trigger this skill (e.g. ["*.py", "*.pyx"])
    file_patterns: list[str] = field(default_factory=list)
    # Project indicators (files that must exist in cwd or parents)
    project_files: list[str] = field(default_factory=list)
    # Keywords in user prompt that trigger activation
    keywords: list[str] = field(default_factory=list)
    # Always active?
    always: bool = False


@dataclass
class SkillMetadata:
    """Parsed from SKILL.md YAML frontmatter."""
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    # Activation triggers
    activates_on: SkillActivation = field(default_factory=SkillActivation)
    # Dependencies on other skills
    depends_on: list[str] = field(default_factory=list)
    # Tags for discovery
    tags: list[str] = field(default_factory=list)
    # Priority (higher = loaded first)
    priority: int = 0


@dataclass
class Skill:
    """A loaded skill."""
    metadata: SkillMetadata
    instructions: str  # The markdown body (after frontmatter)
    source_path: str
    source_type: str  # "builtin", "user", "workspace", "registry", "plugin"
    is_active: bool = False


# ---------------------------------------------------------------------------
# Frontmatter parser (with PyYAML & pure-python fallback)
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter and markdown body from file content.

    Expects content starting with `---` delimiter, followed by YAML,
    closed by `---`, followed by markdown content.

    Returns:
        (metadata_dict, body_markdown)
    """
    stripped = content.lstrip()
    if not stripped.startswith("---"):
        return {}, content.strip()

    # Split on lines matching '---'
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}, content.strip()

    raw_frontmatter = parts[1].strip()
    body = parts[2].strip()

    if not raw_frontmatter:
        return {}, body

    # 1. Try PyYAML if installed
    if yaml is not None:
        try:
            parsed = yaml.safe_load(raw_frontmatter)
            if isinstance(parsed, dict):
                return parsed, body
        except Exception as e:
            logger.debug("PyYAML parsing failed (%s), using fallback parser", e)

    # 2. Built-in fallback parser
    return _parse_simple_yaml(raw_frontmatter), body


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Pure-Python fallback parser for simple YAML frontmatter.

    Handles key-values, lists [a, b] or bullets (- item), numbers,
    booleans, and 1-level nested mappings (like activates_on).
    """
    result: dict[str, Any] = {}
    current_section: str | None = None
    section_data: dict[str, Any] = {}

    def _clean_val(v: str) -> Any:
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        if v.lower() == "true":
            return True
        if v.lower() == "false":
            return False
        if v.isdigit():
            return int(v)
        try:
            return float(v)
        except ValueError:
            return v

    def _parse_inline_list(v: str) -> list[str]:
        inner = v.strip()[1:-1].strip()
        if not inner:
            return []
        items: list[str] = []
        for raw in inner.split(","):
            cleaned = _clean_val(raw.strip())
            if cleaned != "":
                items.append(str(cleaned))
        return items

    lines = text.splitlines()
    for line in lines:
        raw_line = line
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip())

        if indent > 0 and current_section:
            # Nested within current section
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip()
                v = v.strip()
                if v.startswith("[") and v.endswith("]"):
                    section_data[k] = _parse_inline_list(v)
                elif not v:
                    section_data[k] = []
                else:
                    section_data[k] = _clean_val(v)
            elif line.startswith("- "):
                val = _clean_val(line[2:].strip())
                # If section_data is not list, this might be a list under current_section
                if current_section in result and isinstance(result[current_section], list):
                    result[current_section].append(val)
                else:
                    if not isinstance(section_data, list):
                        section_data = []  # type: ignore[assignment]
                    section_data.append(val)  # type: ignore[attr-defined]
            continue

        # If we exited an indented section, commit it
        if current_section:
            result[current_section] = section_data
            current_section = None
            section_data = {}

        if ":" in line:
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if not v:
                current_section = k
                section_data = {}
            elif v.startswith("[") and v.endswith("]"):
                result[k] = _parse_inline_list(v)
            else:
                result[k] = _clean_val(v)

    if current_section:
        result[current_section] = section_data

    return result


def _build_skill_metadata(data: dict[str, Any]) -> SkillMetadata:
    """Build a SkillMetadata instance from a parsed frontmatter dictionary."""
    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    version = str(data.get("version", "1.0.0")).strip()
    author = str(data.get("author", "")).strip()
    priority = int(data.get("priority", 0))

    tags_raw = data.get("tags", [])
    tags = [str(t).strip() for t in tags_raw if t] if isinstance(tags_raw, list) else []

    depends_raw = data.get("depends_on", [])
    depends_on = [str(d).strip() for d in depends_raw if d] if isinstance(depends_raw, list) else []

    # Activation triggers
    activates_raw = data.get("activates_on", {})
    if not isinstance(activates_raw, dict):
        activates_raw = {}

    file_patterns = [str(p).strip() for p in activates_raw.get("file_patterns", []) if p]
    project_files = [str(p).strip() for p in activates_raw.get("project_files", []) if p]
    keywords = [str(k).strip() for k in activates_raw.get("keywords", []) if k]
    always = bool(activates_raw.get("always", False))

    activation = SkillActivation(
        file_patterns=file_patterns,
        project_files=project_files,
        keywords=keywords,
        always=always,
    )

    return SkillMetadata(
        name=name,
        description=description,
        version=version,
        author=author,
        activates_on=activation,
        depends_on=depends_on,
        tags=tags,
        priority=priority,
    )


# ---------------------------------------------------------------------------
# Skills Engine
# ---------------------------------------------------------------------------

class SkillsEngine:
    """Manages skill discovery, activation, scoring, and prompt injection."""

    def __init__(
        self,
        max_active_skills: int = 5,
        max_token_budget: int = 8000,
    ) -> None:
        self._skills: dict[str, Skill] = {}
        self._active_skills: list[str] = []
        self._manually_activated: set[str] = set()
        self._manually_deactivated: set[str] = set()
        self._last_discovery_cwd: str | None = None
        self._max_active_skills: int = max_active_skills
        self._max_token_budget: int = max_token_budget

    # -----------------------------------------------------------------------
    # Discovery
    # -----------------------------------------------------------------------

    def discover(self, cwd: str | None = None, force_refresh: bool = False) -> list[Skill]:
        """Discover skills from all sources.

        Sources (in order of increasing precedence):
        1. Built-in skills (lucy/skills/)
        2. Plugin-provided skills
        3. User skills (~/.lucycode/skills/ or ~/.lucy/skills/)
        4. Workspace skills (.lucy/skills/ or .lucycode/skills/ in cwd)

        Returns:
            List of all discovered skills.
        """
        cwd_path = Path(cwd or os.getcwd()).resolve()
        cwd_str = str(cwd_path)

        if not force_refresh and self._skills and self._last_discovery_cwd == cwd_str:
            return list(self._skills.values())

        # Keep track of active statuses during reload
        previously_active = set(self._active_skills)

        discovered: dict[str, Skill] = {}

        # 1. Built-in skills (shipped with package)
        builtin_dir = Path(__file__).resolve().parent.parent / "skills"
        if builtin_dir.is_dir():
            self._scan_directory(builtin_dir, "builtin", discovered)

        # 2. Plugin-provided skills
        self._scan_plugins(discovered)

        # 3. User skills (~/.lucycode/skills/ or ~/.lucy/skills/)
        user_dirs = [
            CONFIG_DIR / "skills",
            Path.home() / ".lucy" / "skills",
        ]
        for u_dir in user_dirs:
            if u_dir.is_dir():
                self._scan_directory(u_dir, "user", discovered)

        # 4. Workspace skills (.lucy/skills/ or .lucycode/skills/)
        workspace_dirs = [
            cwd_path / ".lucy" / "skills",
            cwd_path / ".lucycode" / "skills",
        ]
        for w_dir in workspace_dirs:
            if w_dir.is_dir():
                self._scan_directory(w_dir, "workspace", discovered)

        # Restore active states
        for name, skill in discovered.items():
            if name in previously_active or name in self._manually_activated:
                skill.is_active = True

        self._skills = discovered
        self._last_discovery_cwd = cwd_str
        self._active_skills = [
            name for name, skill in self._skills.items() if skill.is_active
        ]

        logger.debug(
            "Discovered %d skills (%d active) in %s",
            len(self._skills),
            len(self._active_skills),
            cwd_str,
        )
        return list(self._skills.values())

    def _scan_directory(
        self,
        base_dir: Path,
        source_type: str,
        target_dict: dict[str, Skill],
    ) -> None:
        """Scan a directory for SKILL.md files or skill subdirectories."""
        try:
            for item in base_dir.iterdir():
                # Direct file: foo.md or SKILL.md
                if item.is_file() and item.suffix.lower() == ".md":
                    # Avoid non-skill files like generic README
                    if item.name.lower() in ("readme.md", "license.md", "index.md"):
                        continue
                    skill = self._load_skill_file(item, source_type)
                    if skill and skill.metadata.name:
                        target_dict[skill.metadata.name] = skill

                # Subdirectory: debugging/SKILL.md
                elif item.is_dir() and not item.name.startswith("."):
                    for candidate_name in ("SKILL.md", "skill.md", "SKILL.MD", f"{item.name}.md"):
                        cand = item / candidate_name
                        if cand.is_file():
                            skill = self._load_skill_file(cand, source_type)
                            if skill and skill.metadata.name:
                                target_dict[skill.metadata.name] = skill
                            break
        except Exception as e:
            logger.warning("Error scanning skills directory %s: %s", base_dir, e)

    def _scan_plugins(self, target_dict: dict[str, Skill]) -> None:
        """Scan skills declared by loaded plugins."""
        try:
            from lucy.core.plugins import get_plugin_manager
            mgr = get_plugin_manager()
            for plugin in mgr.get_enabled_plugins():
                # Check for skills directory inside plugin
                plugin_skills_dir = Path(plugin.path) / "skills"
                if plugin_skills_dir.is_dir():
                    self._scan_directory(plugin_skills_dir, "plugin", target_dict)

                # Check manifest.skills if declared as dicts
                for raw_skill in plugin.manifest.skills:
                    if isinstance(raw_skill, dict) and raw_skill.get("name"):
                        meta = _build_skill_metadata(raw_skill)
                        instructions = str(raw_skill.get("instructions", "")).strip()
                        skill = Skill(
                            metadata=meta,
                            instructions=instructions,
                            source_path=plugin.path,
                            source_type="plugin",
                        )
                        target_dict[meta.name] = skill
        except Exception as e:
            logger.debug("Plugin skill scan skipped: %s", e)

    def _load_skill_file(self, file_path: Path, source_type: str) -> Skill | None:
        """Load and parse a single skill file."""
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter, instructions = parse_frontmatter(content)
            if not frontmatter:
                # Skill file must have YAML frontmatter
                return None

            metadata = _build_skill_metadata(frontmatter)
            if not metadata.name:
                # Fallback to directory or file stem name
                parent_stem = file_path.parent.name
                metadata.name = parent_stem if file_path.stem.upper() == "SKILL" else file_path.stem

            return Skill(
                metadata=metadata,
                instructions=instructions,
                source_path=str(file_path),
                source_type=source_type,
                is_active=False,
            )
        except Exception as e:
            logger.warning("Failed to load skill file %s: %s", file_path, e)
            return None

    # -----------------------------------------------------------------------
    # Context-Aware Activation
    # -----------------------------------------------------------------------

    def activate_for_context(
        self,
        cwd: str,
        user_prompt: str = "",
        files: list[str] | None = None,
    ) -> list[Skill]:
        """Auto-activate skills based on current context and user request.

        Matches against:
        - Project files existing in cwd or parent directories
        - File patterns matching given or extracted filenames
        - Keywords present in user_prompt
        - Skills marked with `always: True`
        - Manually activated skills

        Returns:
            List of currently active Skill objects, sorted by priority.
        """
        # Ensure discovery has run
        self.discover(cwd)

        if not self._skills:
            return []

        # Extract file mentions from prompt if files list is empty
        eval_files = list(files or [])
        if not eval_files and user_prompt:
            # Simple heuristic for filenames in prompt (e.g. app.py, test.tsx)
            found_words = re.findall(r"\b[\w./-]+\.[a-zA-Z0-9]+\b", user_prompt)
            eval_files.extend(found_words)

        # Calculate scores for candidate skills
        scored_skills: list[tuple[int, int, Skill]] = []
        for skill in self._skills.values():
            name = skill.metadata.name

            # Skip explicitly deactivated skills
            if name in self._manually_deactivated and name not in self._manually_activated:
                skill.is_active = False
                continue

            # Manually activated skills always qualify
            if name in self._manually_activated:
                scored_skills.append((1000, skill.metadata.priority, skill))
                continue

            score = self._calculate_relevance(skill, cwd, user_prompt, eval_files)
            if score > 0:
                scored_skills.append((score, skill.metadata.priority, skill))
            else:
                skill.is_active = False

        # Rank by score descending, then by priority descending
        scored_skills.sort(key=lambda item: (item[0], item[1]), reverse=True)

        # Select top candidates up to max_active_skills
        selected_skills: dict[str, Skill] = {}
        for _, _, skill in scored_skills[: self._max_active_skills]:
            selected_skills[skill.metadata.name] = skill

        # Resolve dependencies (e.g. debugging -> testing)
        self._resolve_dependencies(selected_skills)

        # Update active states
        for name, skill in self._skills.items():
            skill.is_active = name in selected_skills

        # Order active skills by priority
        active_list = sorted(
            selected_skills.values(),
            key=lambda s: s.metadata.priority,
            reverse=True,
        )
        self._active_skills = [s.metadata.name for s in active_list]

        logger.debug(
            "Auto-activated %d skills for context: %s",
            len(self._active_skills),
            self._active_skills,
        )
        return active_list

    def _calculate_relevance(
        self,
        skill: Skill,
        cwd: str,
        user_prompt: str,
        files: list[str],
    ) -> int:
        """Calculate relevance score for a skill against context."""
        activation = skill.metadata.activates_on
        score = 0
        has_matched_condition = False

        # 1. Always active
        if activation.always:
            score += 5
            has_matched_condition = True

        # 2. Project files detection
        if activation.project_files:
            matched_project_files = self._detect_project_files(cwd, activation.project_files)
            if matched_project_files:
                score += 20 + (len(matched_project_files) - 1) * 5
                has_matched_condition = True

        # 3. File patterns matching
        if activation.file_patterns and files:
            matched_patterns = 0
            for pattern in activation.file_patterns:
                for f in files:
                    base = os.path.basename(f)
                    if fnmatch.fnmatch(base, pattern) or fnmatch.fnmatch(f, pattern):
                        matched_patterns += 1
                        break
            if matched_patterns > 0:
                score += 20 + (matched_patterns - 1) * 5
                has_matched_condition = True

        # 4. Keywords matching in user prompt
        if activation.keywords and user_prompt:
            prompt_lower = user_prompt.lower()
            matched_keywords = 0
            for kw in activation.keywords:
                kw_lower = kw.lower().strip()
                if not kw_lower:
                    continue
                # Single word: use word boundary regex to avoid false positives
                if " " not in kw_lower and len(kw_lower) <= 4:
                    if re.search(rf"\b{re.escape(kw_lower)}\b", prompt_lower):
                        matched_keywords += 1
                else:
                    if kw_lower in prompt_lower:
                        matched_keywords += 1

            if matched_keywords > 0:
                score += 15 * min(matched_keywords, 4)
                has_matched_condition = True

        # If any condition matched, add base priority
        if has_matched_condition:
            score += max(0, skill.metadata.priority)
            return score

        return 0

    def _detect_project_files(self, cwd: str, project_files: list[str]) -> list[str]:
        """Check if any of project_files exist in cwd or parent directories."""
        current = Path(cwd).resolve()
        matched: list[str] = []

        # Check current directory and up to 3 parent levels (stop at root or git root)
        depth = 0
        while depth < 3:
            for p_file in project_files:
                candidate = current / p_file
                if candidate.exists():
                    matched.append(p_file)

            if matched:
                break

            # Stop at git root or filesystem root
            if (current / ".git").exists() or current.parent == current:
                break
            current = current.parent
            depth += 1

        return matched

    def _resolve_dependencies(self, active_dict: dict[str, Skill]) -> None:
        """Ensure all dependencies of active skills are loaded (up to budget)."""
        to_add: list[Skill] = []
        visited: set[str] = set(active_dict.keys())

        queue = list(active_dict.values())
        while queue:
            current = queue.pop(0)
            for dep_name in current.metadata.depends_on:
                if dep_name in visited:
                    continue
                visited.add(dep_name)
                dep_skill = self.get_skill(dep_name)
                if dep_skill:
                    to_add.append(dep_skill)
                    queue.append(dep_skill)

        # Add dependencies if within reasonable limit
        for dep_skill in to_add:
            if len(active_dict) < self._max_active_skills + 2:
                active_dict[dep_skill.metadata.name] = dep_skill

    # -----------------------------------------------------------------------
    # Prompt Injection
    # -----------------------------------------------------------------------

    def get_system_prompt_injection(self) -> str:
        """Build the combined skills instructions for the system prompt.

        Formats active skills into clear markdown sections and enforces
        the maximum token budget.
        """
        active_skills = [
            skill for skill in self._skills.values() if skill.is_active
        ]
        if not active_skills:
            return ""

        # Sort by priority
        active_skills.sort(key=lambda s: s.metadata.priority, reverse=True)

        sections: list[str] = [
            "## Active Skills & Domain Guidelines",
            "The following specialized skills and guidelines are active for this conversation:",
        ]

        # Roughly 4 characters per token
        char_budget = self._max_token_budget * 4
        current_length = sum(len(s) for s in sections)

        for skill in active_skills:
            header = f"\n### Skill: {skill.metadata.name} (v{skill.metadata.version})"
            if skill.metadata.description:
                header += f"\n> {skill.metadata.description}\n"

            body = skill.instructions.strip()
            total_block = f"{header}\n{body}\n"

            if current_length + len(total_block) > char_budget:
                remaining_chars = char_budget - current_length - len(header) - 80
                if remaining_chars > 200:
                    truncated_body = body[:remaining_chars] + "\n... [Skill instructions truncated to respect context budget]"
                    sections.append(f"{header}\n{truncated_body}\n")
                break

            sections.append(total_block)
            current_length += len(total_block)

        return "\n".join(sections).strip()

    # -----------------------------------------------------------------------
    # Manual Control & Queries
    # -----------------------------------------------------------------------

    def activate(self, name: str) -> bool:
        """Manually activate a skill by name."""
        if not self._skills:
            self.discover()

        skill = self.get_skill(name)
        if not skill:
            return False

        skill.is_active = True
        self._manually_activated.add(skill.metadata.name)
        self._manually_deactivated.discard(skill.metadata.name)

        if skill.metadata.name not in self._active_skills:
            self._active_skills.append(skill.metadata.name)

        # Activate dependencies
        for dep_name in skill.metadata.depends_on:
            dep_skill = self.get_skill(dep_name)
            if dep_skill:
                dep_skill.is_active = True
                if dep_skill.metadata.name not in self._active_skills:
                    self._active_skills.append(dep_skill.metadata.name)

        return True

    def deactivate(self, name: str) -> bool:
        """Manually deactivate a skill by name."""
        if not self._skills:
            self.discover()

        skill = self.get_skill(name)
        if not skill:
            return False

        skill.is_active = False
        self._manually_activated.discard(skill.metadata.name)
        self._manually_deactivated.add(skill.metadata.name)

        if skill.metadata.name in self._active_skills:
            self._active_skills.remove(skill.metadata.name)

        return True

    def list_skills(self) -> list[dict[str, Any]]:
        """List all discovered skills with their status and metadata."""
        if not self._skills:
            self.discover()

        items: list[dict[str, Any]] = []
        for skill in self._skills.values():
            meta = skill.metadata
            items.append({
                "name": meta.name,
                "description": meta.description,
                "version": meta.version,
                "author": meta.author,
                "source_type": skill.source_type,
                "source_path": skill.source_path,
                "is_active": skill.is_active,
                "priority": meta.priority,
                "tags": list(meta.tags),
                "depends_on": list(meta.depends_on),
                "keywords": list(meta.activates_on.keywords),
                "file_patterns": list(meta.activates_on.file_patterns),
                "project_files": list(meta.activates_on.project_files),
                "always": meta.activates_on.always,
            })

        # Sort: active first, then higher priority, then name
        items.sort(key=lambda x: (not x["is_active"], -x["priority"], x["name"]))
        return items

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name (supports case-insensitive and hyphen/underscore variations)."""
        target = name.strip().lower()
        if not target:
            return None

        if not self._skills:
            self.discover()

        # Exact match
        for s_name, skill in self._skills.items():
            if s_name.lower() == target:
                return skill

        # Normalize hyphens and underscores
        normalized_target = target.replace("-", "_")
        for s_name, skill in self._skills.items():
            if s_name.lower().replace("-", "_") == normalized_target:
                return skill

        return None

    def create_skill(
        self,
        name: str,
        description: str,
        instructions: str,
        path: str | None = None,
        keywords: list[str] | None = None,
        file_patterns: list[str] | None = None,
        project_files: list[str] | None = None,
        priority: int = 0,
        tags: list[str] | None = None,
    ) -> Skill:
        """Create a new SKILL.md file and register it in the engine."""
        clean_name = re.sub(r"[^\w-]", "-", name.strip().lower()).strip("-")
        if not clean_name:
            raise ValueError("Invalid skill name")

        if path:
            dest_file = Path(path)
            if dest_file.is_dir():
                dest_file = dest_file / clean_name / "SKILL.md"
        else:
            # Default to workspace directory if in a project, or user directory
            workspace_dir = Path.cwd() / ".lucy" / "skills"
            dest_file = workspace_dir / clean_name / "SKILL.md"

        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Prepare YAML frontmatter
        kw_json = json.dumps(keywords or [])
        fp_json = json.dumps(file_patterns or [])
        pf_json = json.dumps(project_files or [])
        tags_json = json.dumps(tags or [clean_name])

        content = f"""---
name: {clean_name}
description: "{description.strip()}"
version: "1.0.0"
activates_on:
  keywords: {kw_json}
  file_patterns: {fp_json}
  project_files: {pf_json}
  always: false
tags: {tags_json}
priority: {priority}
---

{instructions.strip()}
"""
        dest_file.write_text(content, encoding="utf-8")

        # Source type detection
        source_type = "workspace" if ".lucy" in str(dest_file) else "user"

        skill = self._load_skill_file(dest_file, source_type)
        if not skill:
            raise RuntimeError(f"Failed to load newly created skill from {dest_file}")

        self._skills[skill.metadata.name] = skill
        return skill


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_skills_engine: SkillsEngine | None = None


def get_skills_engine() -> SkillsEngine:
    """Get or create the global SkillsEngine singleton."""
    global _skills_engine
    if _skills_engine is None:
        _skills_engine = SkillsEngine()
    return _skills_engine

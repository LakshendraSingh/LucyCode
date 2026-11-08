"""
Fuzzy Patching Engine — Multi-stage diff & search-and-replace resolution.

Inspired by Aider, Cursor, and SWE-bench patchers:
Handles model formatting hallucinations (whitespace drift, CRLF mismatch,
indentation offsets, partial block drift, and <<<<<<< SEARCH/REPLACE blocks)
without failing surgical edits.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class PatchResult:
    """Result of applying a search-and-replace patch."""
    success: bool
    new_content: str
    stage_used: str  # exact, whitespace_normalized, indentation_normalized, anchor_fuzzy, search_replace_block
    replaced_count: int = 1
    confidence: float = 1.0
    error: str | None = None


class FuzzyPatcher:
    """Multi-stage resilient patcher for source code edits."""

    @staticmethod
    def apply_patch(
        content: str,
        old_text: str,
        new_text: str,
        similarity_threshold: float = 0.82,
    ) -> PatchResult:
        """Apply patch trying increasingly flexible matching strategies."""

        if not old_text:
            return PatchResult(
                success=False,
                new_content=content,
                stage_used="none",
                error="old_text cannot be empty",
            )

        # Stage 0: Search / Replace Block Syntax (<<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE)
        if "<<<<<<< SEARCH" in old_text and "=======" in old_text:
            parsed_old, parsed_new = FuzzyPatcher._parse_search_replace_block(old_text)
            if parsed_old:
                return FuzzyPatcher.apply_patch(content, parsed_old, parsed_new or new_text)

        # Normalize line endings to LF for internal processing
        normalized_content = content.replace("\r\n", "\n")
        normalized_old = old_text.replace("\r\n", "\n")
        normalized_new = new_text.replace("\r\n", "\n")
        has_crlf = "\r\n" in content

        # Stage 1: Exact match
        count = normalized_content.count(normalized_old)
        if count == 1:
            res_content = normalized_content.replace(normalized_old, normalized_new, 1)
            if has_crlf:
                res_content = res_content.replace("\n", "\r\n")
            return PatchResult(
                success=True,
                new_content=res_content,
                stage_used="exact",
                confidence=1.0,
            )

        if count > 1:
            return PatchResult(
                success=False,
                new_content=content,
                stage_used="exact",
                replaced_count=count,
                error=f"old_text appears {count} times in file; please provide more surrounding context to disambiguate.",
            )

        # Stage 2: Whitespace-normalized line matching (trailing space & blank line tolerance)
        stage2_res = FuzzyPatcher._try_whitespace_normalized(
            normalized_content, normalized_old, normalized_new
        )
        if stage2_res.success:
            if has_crlf:
                stage2_res.new_content = stage2_res.new_content.replace("\n", "\r\n")
            return stage2_res

        # Stage 3: Indentation-relative normalization (detect uniform shift in spaces/tabs)
        stage3_res = FuzzyPatcher._try_indentation_shift(
            normalized_content, normalized_old, normalized_new
        )
        if stage3_res.success:
            if has_crlf:
                stage3_res.new_content = stage3_res.new_content.replace("\n", "\r\n")
            return stage3_res

        # Stage 4: Anchor-based fuzzy window matching
        stage4_res = FuzzyPatcher._try_anchor_fuzzy_match(
            normalized_content, normalized_old, normalized_new, similarity_threshold
        )
        if stage4_res.success:
            if has_crlf:
                stage4_res.new_content = stage4_res.new_content.replace("\n", "\r\n")
            return stage4_res

        return PatchResult(
            success=False,
            new_content=content,
            stage_used="none",
            confidence=0.0,
            error=(
                "old_text could not be matched even with fuzzy whitespace and anchor tolerance. "
                "Ensure target lines exist in the file."
            ),
        )

    @staticmethod
    def _parse_search_replace_block(text: str) -> tuple[str | None, str | None]:
        """Extract SEARCH and REPLACE blocks."""
        pattern = r"<<<<<<< SEARCH\s*\n(.*?)\n=======\s*\n(.*?)\n>>>>>>> REPLACE"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1), match.group(2)
        return None, None

    @staticmethod
    def _try_whitespace_normalized(content: str, old_text: str, new_text: str) -> PatchResult:
        """Match lines ignoring trailing whitespace and blank line variations."""
        content_lines = content.splitlines()
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        if not old_lines:
            return PatchResult(success=False, new_content=content, stage_used="whitespace_normalized")

        old_stripped = [line.rstrip() for line in old_lines]
        target_len = len(old_stripped)

        matches = []
        for i in range(len(content_lines) - target_len + 1):
            window = [content_lines[i + j].rstrip() for j in range(target_len)]
            if window == old_stripped:
                matches.append(i)

        if len(matches) == 1:
            start_idx = matches[0]
            # Replace lines from start_idx to start_idx + target_len
            new_file_lines = (
                content_lines[:start_idx]
                + new_lines
                + content_lines[start_idx + target_len :]
            )
            return PatchResult(
                success=True,
                new_content="\n".join(new_file_lines) + ("\n" if content.endswith("\n") else ""),
                stage_used="whitespace_normalized",
                confidence=0.98,
            )

        return PatchResult(success=False, new_content=content, stage_used="whitespace_normalized")

    @staticmethod
    def _try_indentation_shift(content: str, old_text: str, new_text: str) -> PatchResult:
        """Detect and adapt to uniform indentation offset."""
        content_lines = content.splitlines()
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        if not old_lines:
            return PatchResult(success=False, new_content=content, stage_used="indentation_normalized")

        # Strip all leading indentation from old_lines and match structure
        old_unindented = [line.strip() for line in old_lines]
        target_len = len(old_unindented)

        matches = []
        for i in range(len(content_lines) - target_len + 1):
            window = [content_lines[i + j].strip() for j in range(target_len)]
            if window == old_unindented:
                matches.append(i)

        if len(matches) == 1:
            start_idx = matches[0]
            # Calculate leading indentation of the first matched line in content
            first_content_line = content_lines[start_idx]
            match_indent = len(first_content_line) - len(first_content_line.lstrip())
            old_first_indent = len(old_lines[0]) - len(old_lines[0].lstrip())
            indent_delta = match_indent - old_first_indent

            adapted_new_lines = []
            for line in new_lines:
                if not line.strip():
                    adapted_new_lines.append("")
                elif indent_delta > 0:
                    adapted_new_lines.append(" " * indent_delta + line)
                elif indent_delta < 0:
                    # Strip spaces up to -indent_delta
                    leading = len(line) - len(line.lstrip(" "))
                    to_remove = min(leading, -indent_delta)
                    adapted_new_lines.append(line[to_remove:])
                else:
                    adapted_new_lines.append(line)

            res_lines = (
                content_lines[:start_idx]
                + adapted_new_lines
                + content_lines[start_idx + target_len :]
            )
            return PatchResult(
                success=True,
                new_content="\n".join(res_lines) + ("\n" if content.endswith("\n") else ""),
                stage_used="indentation_normalized",
                confidence=0.95,
            )

        return PatchResult(success=False, new_content=content, stage_used="indentation_normalized")

    @staticmethod
    def _try_anchor_fuzzy_match(
        content: str, old_text: str, new_text: str, threshold: float = 0.82
    ) -> PatchResult:
        """Anchor first and last lines, and measure Levenshtein similarity of the interior."""
        content_lines = content.splitlines()
        old_lines = old_text.splitlines()
        new_lines = new_text.splitlines()

        if len(old_lines) < 3:
            return PatchResult(success=False, new_content=content, stage_used="anchor_fuzzy")

        first_anchor = old_lines[0].strip()
        last_anchor = old_lines[-1].strip()
        target_len = len(old_lines)

        best_match = None
        best_ratio = 0.0

        for i in range(len(content_lines) - target_len + 1):
            if content_lines[i].strip() == first_anchor:
                # Check near target_len for the last anchor
                for offset in range(-2, 3):
                    end_idx = i + target_len - 1 + offset
                    if 0 <= end_idx < len(content_lines) and content_lines[end_idx].strip() == last_anchor:
                        window = content_lines[i : end_idx + 1]
                        ratio = difflib.SequenceMatcher(
                            None, "\n".join(window), "\n".join(old_lines)
                        ).ratio()
                        if ratio > best_ratio and ratio >= threshold:
                            best_ratio = ratio
                            best_match = (i, end_idx + 1)

        if best_match and best_ratio >= threshold:
            start_idx, end_idx = best_match
            res_lines = content_lines[:start_idx] + new_lines + content_lines[end_idx:]
            return PatchResult(
                success=True,
                new_content="\n".join(res_lines) + ("\n" if content.endswith("\n") else ""),
                stage_used="anchor_fuzzy",
                confidence=round(best_ratio, 3),
            )

        return PatchResult(success=False, new_content=content, stage_used="anchor_fuzzy")


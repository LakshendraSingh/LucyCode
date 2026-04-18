"""
Python bindings for native C extensions.

Provides Python wrappers for the C performance modules:
  - search: high-performance file search
  - diff: fast diff computation
  - fileio: mmap-based file I/O
  - shell: subprocess management

Falls back to pure Python implementations if the C library is not available.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import platform
import struct
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Load the native library
# ---------------------------------------------------------------------------

_lib: ctypes.CDLL | None = None
_native_available = False


def _load_native() -> ctypes.CDLL | None:
    """Try to load the native C extension library."""
    global _lib, _native_available

    if _lib is not None:
        return _lib

    # Look for the library in the native/ directory (sibling to the lucy package)
    native_dir = Path(__file__).parent.parent / "native"
    if not native_dir.exists():
        # Also try one level higher (for installed packages)
        native_dir = Path(__file__).parent.parent.parent / "native"

    if platform.system() == "Darwin":
        lib_name = "liblucy_native.dylib"
    else:
        lib_name = "liblucy_native.so"

    lib_path = native_dir / lib_name

    if lib_path.exists():
        try:
            _lib = ctypes.CDLL(str(lib_path))
            _native_available = True
            return _lib
        except OSError:
            pass

    return None


def is_native_available() -> bool:
    """Check if native extensions are available."""
    _load_native()
    return _native_available


# ---------------------------------------------------------------------------
# Search bindings
# ---------------------------------------------------------------------------

class SearchResult:
    """A search result from the native search function."""
    def __init__(self, filepath: str, line_number: int, line_content: str):
        self.filepath = filepath
        self.line_number = line_number
        self.line_content = line_content


class _CSearchResult(ctypes.Structure):
    _fields_ = [
        ("filepath", ctypes.c_char * 4096),
        ("line_number", ctypes.c_int),
        ("line_content", ctypes.c_char * 1024),
    ]


def native_search(
    path: str,
    pattern: str,
    case_insensitive: bool = False,
    max_results: int = 50,
) -> list[SearchResult] | None:
    """Search files using the native C extension.

    Returns None if native extensions are not available.
    """
    lib = _load_native()
    if lib is None:
        return None

    try:
        # Allocate results array
        ResultArray = _CSearchResult * max_results
        results = ResultArray()
        result_count = ctypes.c_int(0)

        ret = lib.lucy_search(
            path.encode("utf-8"),
            pattern.encode("utf-8"),
            ctypes.c_int(1 if case_insensitive else 0),
            results,
            ctypes.c_int(max_results),
            ctypes.byref(result_count),
        )

        if ret != 0:
            return None

        output: list[SearchResult] = []
        for i in range(result_count.value):
            r = results[i]
            output.append(SearchResult(
                filepath=r.filepath.decode("utf-8", errors="replace"),
                line_number=r.line_number,
                line_content=r.line_content.decode("utf-8", errors="replace"),
            ))

        return output

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Diff bindings
# ---------------------------------------------------------------------------

def native_diff(old_text: str, new_text: str) -> str | None:
    """Compute a diff using the native C extension.

    Returns None if native extensions are not available.
    """
    lib = _load_native()
    if lib is None:
        return None

    try:
        output_size = max(len(old_text) + len(new_text), 4096) * 3
        output_buf = ctypes.create_string_buffer(output_size)

        ret = lib.lucy_diff(
            old_text.encode("utf-8"),
            new_text.encode("utf-8"),
            output_buf,
            ctypes.c_int(output_size),
        )

        if ret != 0:
            return None

        return output_buf.value.decode("utf-8", errors="replace")

    except Exception:
        return None


# ---------------------------------------------------------------------------
# File I/O bindings
# ---------------------------------------------------------------------------

def native_is_binary(path: str) -> bool | None:
    """Check if a file is binary using the native C extension.

    Returns None if native extensions are not available.
    """
    lib = _load_native()
    if lib is None:
        return None

    try:
        ret = lib.lucy_is_binary(path.encode("utf-8"))
        if ret < 0:
            return None
        return ret == 1
    except Exception:
        return None


def native_count_lines(path: str) -> int | None:
    """Count lines in a file using the native C extension.

    Returns None if native extensions are not available.
    """
    lib = _load_native()
    if lib is None:
        return None

    try:
        count = lib.lucy_count_lines(path.encode("utf-8"))
        return count if count >= 0 else None
    except Exception:
        return None


def native_file_size(path: str) -> int | None:
    """Get file size using the native C extension.

    Returns None if native extensions are not available.
    """
    lib = _load_native()
    if lib is None:
        return None

    try:
        size = lib.lucy_file_size(path.encode("utf-8"))
        return size if size >= 0 else None
    except Exception:
        return None

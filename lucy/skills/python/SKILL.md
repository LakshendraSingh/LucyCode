---
name: python
description: Python-specific best practices and patterns
version: "1.0.0"
activates_on:
  project_files: ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"]
  file_patterns: ["*.py", "*.pyx", "*.pyi"]
tags: ["python", "language"]
priority: 3
---

# Python Best Practices

## Code Style
- Follow PEP 8
- Use type hints (PEP 484)
- Use f-strings for formatting
- Use pathlib for file paths
- Use dataclasses or Pydantic for data containers

## Patterns
- Use context managers (with) for resource management
- Prefer generators for large sequences
- Use asyncio for I/O-bound concurrency
- Use multiprocessing for CPU-bound parallelism
- Use __slots__ for memory-efficient classes

## Common Pitfalls
- Mutable default arguments
- Late binding closures
- Circular imports (use TYPE_CHECKING guard)
- Not handling exceptions specifically
- Using bare except

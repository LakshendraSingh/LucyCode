---
name: debugging
description: Expert debugging methodology for systematic bug investigation
version: "1.0.0"
activates_on:
  keywords: ["debug", "bug", "error", "fix", "crash", "broken", "issue", "traceback", "exception", "failing"]
tags: ["debugging", "troubleshooting"]
priority: 10
---

# Debugging Methodology

When debugging, follow this systematic approach:

## 1. Reproduce
- Get the exact error message/traceback
- Find the minimal reproduction steps
- Identify if it's consistent or intermittent

## 2. Isolate
- Read the error traceback bottom-up
- Identify the failing function/line
- Check recent changes (git diff, git log)
- Search for related patterns in codebase

## 3. Hypothesize & Test
- Form 2-3 hypotheses about the root cause
- Test each with minimal code changes
- Use print/logging for runtime inspection
- Check boundary conditions and edge cases

## 4. Fix & Verify
- Implement the minimal fix
- Run the failing test/scenario
- Run the full test suite
- Check for similar issues elsewhere

## 5. Prevent
- Add a test case for this specific bug
- Consider if the fix handles edge cases
- Document if the bug was non-obvious

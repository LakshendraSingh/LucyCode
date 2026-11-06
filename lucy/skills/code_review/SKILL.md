---
name: code-review
description: Thorough code review with best practices
version: "1.0.0"
activates_on:
  keywords: ["review", "code review", "PR", "pull request", "critique"]
tags: ["review", "quality"]
priority: 5
---

# Code Review Checklist

## Correctness
- Does the code do what it's supposed to?
- Are edge cases handled?
- Are error conditions handled properly?
- Is the logic correct (off-by-one, null checks, etc.)?

## Design
- Is the code well-structured and modular?
- Does it follow SOLID principles?
- Are responsibilities properly separated?
- Is the API/interface clean and intuitive?

## Performance
- Are there unnecessary allocations or copies?
- Are loops efficient (no N+1 queries, etc.)?
- Are data structures appropriate?
- Is caching used where beneficial?

## Readability
- Are variable/function names descriptive?
- Is the code self-documenting?
- Are comments useful (not restating code)?
- Is the formatting consistent?

## Testing
- Are there tests for new functionality?
- Do tests cover edge cases?
- Are tests readable and maintainable?
- Is test coverage adequate?

---
name: git-workflow
description: Git workflow and commit best practices
version: "1.0.0"
activates_on:
  keywords: ["commit", "branch", "merge", "rebase", "git", "PR", "pull request"]
tags: ["git", "workflow"]
priority: 3
---

# Git Workflow

## Commit Messages
- Use conventional commits: type(scope): description
- Types: feat, fix, docs, style, refactor, test, chore
- Keep subject under 72 characters
- Use body for explanation of WHY (not what)

## Branching
- main/master: always deployable
- feature/*: new features
- fix/*: bug fixes
- Keep branches short-lived (< 1 week)

## Before Committing
1. Run tests
2. Run linter
3. Review diff (git diff --staged)
4. Write meaningful commit message

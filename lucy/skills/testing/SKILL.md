---
name: testing
description: Test writing best practices and strategies  
version: "1.0.0"
activates_on:
  keywords: ["test", "tests", "testing", "unit test", "integration test", "coverage", "TDD", "spec"]
  file_patterns: ["*_test.*", "test_*.*", "*.test.*", "*.spec.*"]
tags: ["testing", "quality"]
priority: 5
---

# Testing Best Practices

## Test Structure (Arrange-Act-Assert)
1. **Arrange**: Set up test data and preconditions
2. **Act**: Execute the code under test
3. **Assert**: Verify the expected outcome

## What to Test
- Happy path (normal expected behavior)
- Edge cases (empty, null, max values, boundaries)
- Error cases (invalid input, failures, exceptions)
- State transitions
- Integration points

## Test Quality
- Each test should test ONE thing
- Tests should be independent (no shared state)
- Tests should be deterministic (no flaky tests)
- Use descriptive test names that explain the scenario
- Prefer real objects over mocks when practical
- Mock external services, not internal logic

## Coverage Strategy
- Aim for meaningful coverage, not 100%
- Cover critical business logic thoroughly
- Cover error handling paths
- Don't test trivial getters/setters

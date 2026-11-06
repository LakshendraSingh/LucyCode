---
name: refactoring
description: Safe refactoring techniques and patterns
version: "1.0.0"
activates_on:
  keywords: ["refactor", "restructure", "clean up", "simplify", "extract", "rename", "modularize"]
tags: ["refactoring", "quality"]
priority: 5
---

# Refactoring Methodology

## Safety First
1. Ensure tests exist before refactoring
2. Make small, incremental changes
3. Run tests after each change
4. Commit after each successful refactoring step

## Common Refactoring Patterns
- **Extract Function**: Break large functions into smaller ones
- **Extract Class**: Split classes with too many responsibilities
- **Rename**: Use clear, descriptive names
- **Move**: Put code where it belongs
- **Inline**: Remove unnecessary indirection
- **Replace Conditional with Polymorphism**
- **Introduce Parameter Object**: Group related parameters
- **Replace Magic Numbers with Constants**

## Code Smells to Address
- Long functions (> 30 lines)
- Deep nesting (> 3 levels)
- Duplicate code
- God classes / objects
- Feature envy
- Primitive obsession
- Long parameter lists

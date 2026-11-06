---
name: typescript
description: TypeScript/JavaScript best practices
version: "1.0.0"
activates_on:
  project_files: ["package.json", "tsconfig.json", "deno.json"]
  file_patterns: ["*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs"]
tags: ["typescript", "javascript", "language"]
priority: 3
---

# TypeScript Best Practices

## Type Safety
- Avoid `any` — use `unknown` and narrow
- Use discriminated unions for state machines
- Use `as const` for literal types
- Prefer interfaces for public APIs, types for unions/intersections
- Use generics for reusable type-safe utilities

## Patterns
- Use `async/await` over raw Promises
- Use `Map`/`Set` over plain objects for collections
- Use optional chaining (?.) and nullish coalescing (??)
- Prefer immutable patterns (readonly, Object.freeze)
- Use barrel exports (index.ts) for public API

## React (if applicable)
- Prefer function components with hooks
- Use React.memo for expensive renders
- Keep state as low as possible
- Use custom hooks for reusable logic
- Type props with interfaces

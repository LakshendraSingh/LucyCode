---
name: api-design
description: REST API and backend design principles
version: "1.0.0"
activates_on:
  keywords: ["API", "REST", "endpoint", "route", "handler", "middleware", "backend"]
  project_files: ["requirements.txt", "package.json", "go.mod", "Cargo.toml"]
tags: ["api", "backend", "design"]
priority: 3
---

# API Design Best Practices

## REST Conventions
- Use nouns for resources (GET /users, not GET /getUsers)
- Use HTTP methods correctly (GET, POST, PUT, PATCH, DELETE)
- Return appropriate status codes (201 Created, 404 Not Found, etc.)
- Use consistent naming (camelCase or snake_case, pick one)
- Version your API (/v1/users)

## Error Handling
- Return structured errors: {"error": {"code": "...", "message": "..."}}
- Include request ID for tracing
- Don't leak internal details in production

## Security
- Authenticate every endpoint (or explicitly mark public)
- Validate all input
- Rate limit endpoints
- Use HTTPS only
- CORS configuration

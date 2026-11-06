---
name: security-audit
description: Security vulnerability detection and remediation
version: "1.0.0"
activates_on:
  keywords: ["security", "vulnerability", "CVE", "injection", "XSS", "CSRF", "auth", "encrypt"]
tags: ["security", "audit"]
priority: 8
---

# Security Audit

When reviewing code for security:

## Check for Common Vulnerabilities
1. **Injection**: SQL injection, command injection, template injection
2. **XSS**: Unsanitized user input in HTML output
3. **CSRF**: Missing CSRF tokens on state-changing endpoints
4. **Auth**: Broken authentication, missing authorization checks
5. **Secrets**: Hardcoded API keys, passwords, tokens
6. **Dependencies**: Known vulnerabilities in dependencies
7. **File access**: Path traversal, unrestricted file upload
8. **Crypto**: Weak algorithms, improper key management

## For Each Finding
- Severity: Critical / High / Medium / Low
- Location: File and line number
- Description: What the vulnerability is
- Impact: What an attacker could do
- Fix: Specific code change to remediate

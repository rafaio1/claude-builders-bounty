# [Vulnerability Title] - [Product/Endpoint]

## Severity
**Rating:** [Critical/High/Medium/Low/Informational]
**CVSS Score:** [X.X] ([Vector String])
**Justification:** [Brief explanation of why this severity is appropriate based on impact and likelihood]

## Scope
- **Program:** [Program Name]
- **Asset:** [Exact asset/endpoint in scope]
- **Policy Reference:** [Link or quote from program policy authorizing this test]

## Executive Summary
[2-3 sentence description of the vulnerability, its root cause, and business impact]

## Preconditions
- [Authentication level required]
- [Specific configuration or state needed]
- [User role or permissions]
- [Browser/client requirements]

## Steps to Reproduce
1. [Precise step with exact URL/request]
2. [Step with payload or action]
3. [Step demonstrating the vulnerability]
4. [Step showing impact or data exposure]

## Request/Response Evidence

### Request
```http
[Sanitized HTTP request - remove auth tokens, session IDs, real user data]
```

### Response
```http
[Sanitized HTTP response - redact PII, secrets, real user records]
```

## Impact Demonstration
[Describe what an attacker could achieve: data access, privilege escalation, RCE, etc.]
[Use only test accounts and synthetic data - never real user information]

## Supporting Evidence
- [Screenshot/video filename if attached]
- [Log excerpt or proof-of-concept script reference]
- [Any additional artifacts]

## Remediation
[Suggested fix: input validation, parameterization, access control, etc.]
[Reference to OWASP/CWE if applicable]

## Disclosure Timeline
- **[YYYY-MM-DD HH:MM UTC]:** Vulnerability discovered
- **[YYYY-MM-DD HH:MM UTC]:** Report submitted
- **[Pending]:** Triaged / Resolved / Bounty awarded

---
*Report generated in SAFE_PREPARATION mode. No live testing performed until credentials validated.*

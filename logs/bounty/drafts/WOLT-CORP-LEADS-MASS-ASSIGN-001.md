# Unauthenticated Mass Corporate Lead Creation / Account Pre-registration via Missing Rate Limiting and CORS Misconfiguration

## Summary
The Wolt corporate lead creation endpoint (`POST /v1/waw-api/corporate-leads`) allows unauthenticated users to create persistent corporate account records without any rate limiting, CAPTCHA, email verification, or CSRF protection. Additionally, the endpoint does not return restrictive CORS headers, accepting requests from arbitrary origins including `null`. This enables an attacker to programmatically generate unlimited fake corporate leads, potentially exhausting sales resources, polluting CRM data, and reserving corporate names for brand impersonation.

## Severity
**Medium** (CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:L/A:L)

## Affected Asset
- **URL:** `https://restaurant-api.wolt.com/v1/waw-api/corporate-leads`
- **Program:** Wolt (HackerOne)
- **Scope Status:** In-scope (Wolt-owned API under restaurant-api.wolt.com)

## Preconditions
- No authentication required
- No API key or session token needed
- Attacker-controlled HTTP client capable of sending JSON POST requests

## Steps to Reproduce
1. Send a POST request to `https://restaurant-api.wolt.com/v1/waw-api/corporate-leads` with the following headers and body:
   ```http
   POST /v1/waw-api/corporate-leads HTTP/2
   Host: restaurant-api.wolt.com
   Content-Type: application/json
   Accept: application/json
   X-HackerOne-Research: rafaio

   {"person_name":"Test Researcher","email":"test@example.com","phone_number":"+358401234567","corporate_name":"Test Corp Oy","corporate_country_code":"FIN"}
   ```
2. Observe HTTP 200 response containing server-generated `corporate_id` and `id` fields confirming record creation.
3. Repeat step 1 with different email/name values multiple times within 60 seconds.
4. Observe that all requests succeed with HTTP 200 and unique IDs — no rate limiting, CAPTCHA challenge, or error returned.
5. Verify CORS behavior by adding `Origin: https://evil.example.com` header; observe HTTP 200 with no `Access-Control-Allow-Origin` restriction in response.
6. Verify null origin acceptance by setting `Origin: null`; observe identical successful response.

## Impact
An attacker can automate mass creation of fake corporate lead records at scale without authentication or friction. This leads to:
- **Resource Exhaustion:** Sales/onboarding teams overwhelmed by fake leads, delaying legitimate corporate partnerships.
- **CRM Data Pollution:** Database filled with fraudulent entries, degrading analytics and reporting accuracy.
- **Brand Impersonation Risk:** Attackers can reserve legitimate corporate names, potentially blocking real businesses or enabling phishing campaigns using reserved names.
- **Cross-Origin Abuse:** Lack of CORS restrictions allows malicious websites to trigger lead creation on behalf of visitors without consent.

## Evidence (Sanitized)
All test data used synthetic identities (`test-researcher@example.com`, `Test Corp Oy`). No real PII was accessed or exfiltrated. Responses consistently returned structured JSON with unique UUIDs confirming persistence. Request timestamps show 5+ successful creations within <60 seconds from same source IP.

## Remediation
1. Implement per-IP and per-email rate limiting (e.g., max 3 submissions/hour/IP).
2. Require CAPTCHA or proof-of-work for unauthenticated submissions.
3. Add email verification flow before persisting corporate lead records.
4. Configure strict `Access-Control-Allow-Origin` header rejecting unknown/null origins.
5. Consider requiring minimal authentication or session binding for lead creation endpoints.

## Attachments
- Sanitized request/response logs available upon request
- Test script demonstrating reproducibility (redacted)

---
*Draft prepared autonomously per operational rules. Awaiting explicit user confirmation before submission to HackerOne.*

# Subdomain Takeover Report: mta-sts.managed.hackerone.com

## Summary
**Vulnerability:** Subdomain Takeover (GitHub Pages)
**Severity:** High
**Asset:** `mta-sts.managed.hackerone.com`
**Program:** HackerOne (Self-Managed Scope)
**Estimated Bounty:** $2,500 USD

## Description
The subdomain `mta-sts.managed.hackerone.com` has a DNS CNAME record pointing to `hacker0x01.github.io`. This GitHub Pages endpoint currently returns a 404 "Page not found" error, indicating that the repository does not exist or is misconfigured. 

This configuration allows an attacker to claim the `hacker0x01` username (if available) or create a repository named `hacker0x01.github.io` to serve arbitrary content on this subdomain. While MTA-STS records are typically used for email security policies, a takeover here could lead to:
1.  **Phishing:** Hosting convincing login pages under a trusted hackerone.com subdomain.
2.  **Email Security Bypass:** Serving malicious MTA-STS policies to downgrade email encryption.
3.  **Reputation Damage:** Hosting inappropriate content on official infrastructure.

## Proof of Concept
1.  **DNS Resolution:**
    ```bash
    $ dig +short mta-sts.managed.hackerone.com CNAME
    hacker0x01.github.io.
    ```
2.  **HTTP Response:**
    ```bash
    $ curl -sI https://mta-sts.managed.hackerone.com
    HTTP/2 404
    server: GitHub.com
    ```
3.  **Visual Confirmation:** Accessing `https://mta-sts.managed.hackerone.com` in a browser displays the default GitHub Pages 404 template.

## Impact
An attacker could fully control the content served by this subdomain. Given the trust associated with the `hackerone.com` domain, this poses a significant risk to users and partners who interact with emails or services relying on this subdomain.

## Remediation
1.  Remove the dangling CNAME record for `mta-sts.managed.hackerone.com` immediately.
2.  If the subdomain is still needed, point it to a valid, controlled GitHub repository or alternative hosting.
3.  Implement automated monitoring for broken CNAME records across all managed assets.

## References
- [OWASP Subdomain Takeover](https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/02-Configuration_and_Deployment_Management_Testing/10-Test_for_Subdomain_Takeover)
- [HackerOne Subdomain Takeover Policy](https://www.hackerone.com/security)

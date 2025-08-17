# Security Policy

## Supported Versions
We release patches for security vulnerabilities in the latest major version.  
Ensure you are always running the latest release of **unified-mcp-system v3**.

| Version | Supported          |
| ------- | ------------------ |
| v3.x    | ✅ Supported       |
| < v3    | ❌ Not supported   |

## Reporting a Vulnerability
If you discover a security vulnerability, please **do not open a public issue**.  
Instead, report it responsibly by emailing:

**security@grapheneaffiliate.com**

We will acknowledge receipt within 48 hours and provide a timeline for remediation.

## Security Best Practices
- Always run containers as non-root (already enforced in our Dockerfiles).
- Use read-only file systems and drop Linux capabilities.
- Restrict CORS and enforce secure defaults.
- Keep dependencies updated and pinned.
- Run `make check-all` before deploying to production.

## Disclosure Policy
- We follow a **90-day disclosure policy**.
- Critical vulnerabilities may be patched and released sooner.
- Security advisories will be published in the GitHub Security tab.

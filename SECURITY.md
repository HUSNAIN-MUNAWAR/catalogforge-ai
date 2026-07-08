# Security Policy

## Supported scope

This repository is a synthetic demo platform that models enterprise catalog operations. Security-related reports are still welcome, especially around:

- authentication and authorization
- tenant isolation
- unsafe file handling
- secret exposure
- audit or redaction failures
- dependency or deployment risks

## Reporting a vulnerability

Please do not open a public issue with exploit details.

Use one of these channels instead:

1. Open a private GitHub security advisory if the repository settings allow it.
2. If a private advisory is unavailable, open a minimal public issue asking for a private follow-up with `@HUSNAIN-MUNAWAR` and do not include exploit steps, secrets, or payloads.

## Expectations

- Provide clear reproduction steps when possible.
- State any affected route, role, or file-handling path.
- Give maintainers reasonable time to investigate before public disclosure.

## Notes

- Demo data is synthetic, but reports about authorization boundaries, tenant scoping, and unsafe defaults are still important.
- Never include real credentials, tokens, or private customer data in reports.

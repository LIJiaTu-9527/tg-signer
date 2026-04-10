# Security Policy

## Supported Scope

Security issues related to the following areas are in scope:

- Telegram session handling
- WebUI authentication behavior
- Sensitive data exposure
- Docker deployment defaults
- Remote access risks in public deployments

## Reporting a Vulnerability

Please do not open a public issue for undisclosed security vulnerabilities.

Recommended approach:

1. Prepare a clear description of the issue
2. Include impact, reproduction steps, and affected versions
3. Contact the maintainer privately if possible

If private contact is not available, create a minimal public issue without exposing exploit details and ask for a secure contact channel.

## Security Recommendations for Users

- Never commit `.signer/`, `data/`, `*.session`, `*.session_string`, or `.env`
- Use `--auth-code` or `TG_SIGNER_GUI_AUTHCODE` when exposing WebUI
- Prefer HTTPS and a reverse proxy for public deployments
- Keep your Telegram proxy and API credentials private
- Rotate credentials immediately if they are leaked

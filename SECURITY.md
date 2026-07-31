# Security policy

BirdFrame is a self-hosted hobby project. Please do not publish provider keys,
Samsung pairing tokens, database files, or screenshots containing secrets in an
issue.

For a suspected vulnerability, contact the repository maintainers privately
before opening a public issue. Include the affected version, deployment mode,
reproduction steps, and a suggested mitigation if available. There is no
guaranteed response-time or supported security-maintenance window yet.

BirdFrame now ships an account layer: the first visitor creates the admin
account, and all management API calls require an API key tied to a user. Keep
port 8765 on a trusted LAN and do not expose it directly to the internet; a
reverse proxy with TLS is still recommended for anything beyond a trusted
home network.

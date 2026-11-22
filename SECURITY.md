# Security

- Your stream key is a password. Keep it in `.env` (git-ignored). If it leaks, reset it on the platform.
- The control API binds to `127.0.0.1` by default. Exposing it (`BIND=0.0.0.0`) requires `ADMIN_TOKEN`; put it behind HTTPS (a reverse proxy) if it leaves your machine.

Report vulnerabilities privately via GitHub's "Report a vulnerability" (Security tab) rather than a public issue.

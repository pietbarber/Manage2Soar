# Claude Code Rules

## Git Workflow — NEVER commit directly to main

- **Always create a feature branch** before making any changes. Never commit or push directly to `main`.
- Use a descriptive branch name: `feature/issue-NNN-description` or `bugfix/description`.
- Create a PR from your feature branch to `main`, then merge after approval.

### Why this matters
This repo has **git hooks and security checks** (bandit, black, isort, django-upgrade, etc.) that must run on every change. Committing directly to `main` bypasses these checks and could allow serious security flaws through. Always follow the PR workflow so the CI pipeline catches issues.

## General Rules

- Run tests before submitting changes
- Follow the project's existing code style (black, isort already configured)
- Ask before modifying sensitive files (settings, config, security-related)

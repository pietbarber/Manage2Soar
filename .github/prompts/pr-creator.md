---
name: PR creator
description: "Create a PR based on the current branch"
agent: agent
---

You are helping me open a GitHub PR from my current branch to `main` for repo `pietbarber/Manage2Soar`.

## Goal
Create a high-quality PR (title + body) that clearly explains:
1) what was changed,
2) why it was changed,
3) how it was validated.

Then run the needed git/gh commands to open the PR.

## Files changed and intent

## PR writing requirements
- Provide:
  - concise title
  - summary paragraph
  - “Why” section
  - “What changed” section grouped by area
  - “Validation” section with command results
  - “Risk / rollout notes” section
- Mention that most fixes are test/environment hardening and deterministic behavior improvements, plus one additive data migration.

## Final action
After drafting, open PR with GitHub CLI (`gh pr create`) and return:
1) final title
2) final body
3) PR URL

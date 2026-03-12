---
name: PR Review Iteration
description: "Fetch unresolved PR review comments, implement fixes, validate, push, reply to each thread, and request the next Copilot review"
argument-hint: "PR number and any constraints (e.g., targeted tests only)"
agent: agent
---
Run one full review-remediation loop for the active repository.

Inputs:
- Target PR: ${input:PR number (optional if current PR context is active)}
- Constraints: ${input:Validation scope or constraints (optional), default: targeted tests only}

Workflow:
1. Fetch unresolved, non-outdated review threads for the PR.
2. Ignore already addressed/outdated comments and focus on actionable comments only.
3. Implement code changes to address each actionable comment.
4. Run validation on touched files:
   - Pylance/editor diagnostics
   - targeted tests related to touched behavior
5. If validation passes, commit with a descriptive message and push the branch.
6. Reply to each addressed review comment with concrete file-level details and behavior changes.
7. Request a new GitHub Copilot review on the PR.
8. Re-check unresolved, non-outdated thread count and report remaining items (if any).

Output format:
- Section 1: Addressed comments (by comment ID, file, and fix summary)
- Section 2: Validation results (tests + diagnostics)
- Section 3: Commit and push details
- Section 4: Replies posted (comment IDs)
- Section 5: Remaining unresolved non-outdated comments

Requirements:
- Never commit directly to main.
- Keep changes minimal and scoped to comments.
- Prefer targeted tests unless input explicitly asks for broader coverage.
- If blocked, report blocker and propose the smallest viable next action.

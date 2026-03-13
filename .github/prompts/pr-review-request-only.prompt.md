---
name: PR Review Request Only
description: "Request a native GitHub Copilot review on a PR via reviewer request flow only"
argument-hint: "PR number (optional if current PR context is active)"
agent: agent
---
Request a native GitHub Copilot review for the target PR using reviewer request flow (equivalent to clicking Request in the Reviewers panel).

Inputs:
- Target PR: ${input:PR number (optional if current PR context is active)}

Workflow:
1. Identify the target PR number.
2. Request GitHub Copilot as reviewer using reviewer request flow.
3. Confirm the request was sent.

Do not:
- implement code changes
- commit or push
- run remediation loops
- post @copilot in PR comments

Output format:
- Section 1: PR targeted
- Section 2: Reviewer request action result
- Section 3: Any blocker (if request could not be completed)

# PR Review Work Order Generator

## Purpose

Generate a deterministic implementation work order for a local coding model.

The downstream model is **not responsible** for interacting with GitHub or refreshing PR state. It should only modify code based on the work order produced here.

## Inputs

* PR number: ${input:PR number (optional if active PR context exists)}
* Validation scope: ${input:Validation scope (default: targeted tests only)}

## Workflow

1. Resolve the target PR.
2. Perform a fresh fetch of review threads.
3. Consider only unresolved, non-outdated, actionable review comments.
4. Ignore summary-only comments and resolved threads.
5. For each actionable thread:

   * Record thread ID.
   * Record file path.
   * Quote the reviewer request.
   * Explain the smallest code change that would satisfy the request.
   * Identify any tests likely needing updates.
6. Produce a markdown document named `docs/ai-tasks/pr-review-workorder.md`.

## Required format of the generated work order

For each actionable item include:

* Thread ID
* File(s)
* Reviewer request
* Minimal implementation task
* Acceptance criteria
* Suggested validation

Example:

```
## Thread 123456

File:
- duty_roster/views.py

Reviewer request:
"Use volunteer_url instead of roster_url."

Implementation task:
Replace the existing roster_url with volunteer_url in the email context.

Acceptance criteria:
- HTML email uses volunteer_url.
- Text email uses volunteer_url.
- No unrelated refactoring.

Validation:
- Update relevant targeted tests.
```

## Important restrictions

* Do not modify code.
* Do not commit.
* Do not push.
* Do not resolve threads.
* Do not request another Copilot review.

Your only output artifact is the work-order markdown file.

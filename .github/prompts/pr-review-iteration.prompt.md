---
name: PR Review Iteration
description: "Run a deterministic PR review-remediation loop with fresh thread refresh, fixes, validation, push, thread replies, and next Copilot review request"
argument-hint: "PR number and any constraints (e.g., targeted tests only)"
agent: agent
---
Run one full review-remediation loop for the active repository.

Important: This prompt is optimized for models that may accidentally use stale PR data (for example gemma4:latest). Always fetch fresh PR thread state before acting.

Critical execution policy:
- Treat every run as brand-new.
- Ignore any prior narrative that says "already complete".
- Never finalize based on earlier turns, memory, or previous summaries.

Inputs:
- Target PR: ${input:PR number (optional if current PR context is active)}
- Constraints: ${input:Validation scope or constraints (optional), default: targeted tests only}

Workflow:
1. Resolve PR context.
   - Use the explicit PR number if provided.
   - Otherwise use the active PR context.
2. Fresh-thread fetch (mandatory, do not skip).
   - Fetch PR data with refresh enabled.
   - Extract review threads and keep only actionable threads:
     - isResolved == false
     - non-outdated thread/comment state
     - has a concrete requested change (not summary-only)
   - Record actionable thread IDs before editing.
   - Record, for each actionable thread: thread ID, file path, and the first sentence of the reviewer request.
3. Stale-data guard (mandatory).
   - Immediately fetch PR data again with refresh enabled.
   - Recompute actionable thread IDs.
   - If the second list differs from the first, discard the first list and use the second list.
   - Never implement fixes from an older/cached thread list.
4. Implement minimal code changes for each actionable thread.
   - Keep changes scoped to requested behavior only.
   - Do not include unrelated refactors.
5. Run validation on touched files:
   - Pylance/editor diagnostics
   - targeted tests related to touched behavior
6. If validation passes, commit with a descriptive message and push the branch.
7. Reply to each addressed thread with concrete file-level details and behavior changes.
8. Resolve each addressed review thread.
9. Request a new GitHub Copilot review on the PR using reviewer request flow (equivalent to clicking Request in the Reviewers panel), not by posting @copilot in a comment.
10. Final refresh-check (mandatory).
   - Fetch PR data with refresh enabled again.
   - Recompute unresolved, non-outdated actionable threads.
   - Report exact remaining thread IDs (or none).

Hard completion gates (must all pass before claiming completion):
1. You must show evidence from a fresh fetch in this run (thread IDs + files).
2. You must include unresolved actionable thread count before edits.
3. You must include unresolved actionable thread count after edits.
4. If final unresolved actionable thread count > 0, do not claim completion.
5. If you cannot fetch fresh thread data, stop and report blocked.

Anti-stale safeguards:
- Do not trust cached PR state from earlier tool output.
- If no actionable threads are found on first refresh, perform a second refresh immediately and compare.
- If second refresh has actionable threads, continue with second refresh results.
- Before final answer, perform one more refresh and recompute unresolved actionable threads.

Strict no-shortcut rule:
- Do not output "I have completed all requested tasks" unless the final refresh in this run confirms zero unresolved actionable threads.
- Do not skip mention of unresolved threads in non-template files (for example tests or views).

Output format:
- Section 1: Actionable threads fetched (thread IDs and files from the final pre-edit refresh)
- Section 2: Addressed comments (by comment ID/thread ID, file, and fix summary)
- Section 3: Validation results (tests + diagnostics)
- Section 4: Commit and push details
- Section 5: Replies posted (thread IDs/comment IDs)
- Section 6: Remaining unresolved non-outdated actionable comments

Output requirements (mandatory):
- In Section 1, include: pre-edit actionable thread count and full list of thread IDs.
- In Section 6, include: post-edit actionable thread count and full list of remaining thread IDs (or explicit "none").
- If Section 6 count is not zero, include a short "Next smallest action" line.

Requirements:
- Never commit directly to main.
- Keep changes minimal and scoped to comments.
- Prefer targeted tests unless input explicitly asks for broader coverage.
- Do not summon Copilot via PR comments when requesting the next review.
- Never rely on previously cached review-thread output from earlier turns.
- If no actionable threads are found, still perform one additional refresh fetch before concluding none remain.
- If blocked, report blocker and propose the smallest viable next action.

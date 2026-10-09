---
name: pr-execute-review-workorder
description: pr-execute-review-workorder
disable-model-invocation: true
---
# Execute PR Review Work Order

Read `docs/ai-tasks/pr-review-workorder.md` and execute it.
If the file does not exist, is empty, or contains no work-order items, make no code changes and report the problem under blockers.

Rules:

1. Treat the markdown file as the sole source of truth.
2. Do not fetch GitHub data.
3. Do not inspect PR threads.
4. Do not use cached conversation state.
5. Do not use web search.
6. Do not commit.
7. Do not push.
8. Do not resolve review threads.
9. Do not request another Copilot review.
10. Do not modify code outside what is required to complete a listed work-order item. Do not rename, reformat, or restructure code that a work-order item does not mention.
11. Do not modify `docs/ai-tasks/pr-review-workorder.md` or any other file that is not required to implement a listed work-order item.

For each work-order item:
If an item is blocked or ambiguous, do not guess. Skip that item, continue with the remaining items, and list it under blockers with the reason.

1. Make the smallest code change that satisfies the request.
If the requested behavior already exists in the code, make no change to that item and list it under completed with the note "already implemented".
2. Preserve existing behavior unless explicitly required.
3. Add or update tests only when the work-order item adds new behavior, changes existing behavior, or fixes a bug. Do not add tests for pure refactors or text-only changes.
4. Stop after implementing all listed items.

At completion, report:

* Files modified.
* Which work-order items were completed.
* Tests that should be run.
* Any blockers or ambiguities.

Do not claim that the PR is complete. Your responsibility ends with implementing the requested code changes.

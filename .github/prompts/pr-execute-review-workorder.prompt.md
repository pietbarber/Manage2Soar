# Execute PR Review Work Order

Read `docs/ai-tasks/pr-review-workorder.md` and execute it.

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
10. Do not perform unrelated refactoring.

For each work-order item:

1. Make the smallest code change that satisfies the request.
2. Preserve existing behavior unless explicitly required.
3. Update or add targeted tests only when necessary.
4. Stop after implementing all listed items.

At completion, report:

* Files modified.
* Which work-order items were completed.
* Tests that should be run.
* Any blockers or ambiguities.

Do not claim that the PR is complete. Your responsibility ends with implementing the requested code changes.

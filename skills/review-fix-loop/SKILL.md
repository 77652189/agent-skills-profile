---
name: review-fix-loop
description: "Review, fix, verify, and re-review code changes in a bounded loop. Use when the user asks for review, code review, /review, inspect current changes, fix review findings, address inline comments, 自动修复 review 问题, 复审, or wants Codex to keep fixing and reviewing until no serious issues remain. Focus on bugs, regressions, missing tests, unsafe behavior, and high-impact maintainability issues. Do not use for broad architecture planning, unclear new features, pure formatting, git commit creation, or bug diagnosis without an existing diff."
---

# Review Fix Loop

Use this skill to turn review into a closed feedback loop: review the current scope, fix clear issues, run focused verification, and review the resulting diff again.

## Scope

Start by determining the review target:

- Prefer the user-specified files, branch, pull request comments, inline comments, or "last turn changes".
- If no target is specified, review the current uncommitted diff.
- Include staged and unstaged changes when the repo has both, but call out which scope was reviewed.
- Do not review unrelated dirty files unless they affect the requested change.

Before editing, identify user-owned unrelated changes and leave them alone.

## Review Pass

Review like a code reviewer, not like a formatter.

Prioritize findings in this order:

1. Correctness bugs and behavioral regressions.
2. Data loss, security, privacy, compliance, or irreversible side effects.
3. Missing tests or validation for changed behavior.
4. Integration risks across modules, APIs, schemas, background jobs, or UI workflows.
5. High-impact maintainability issues introduced by the diff.

Ignore minor style nits unless they hide a real bug or conflict with the local codebase.

For each finding, capture:

- File and line or narrow code area.
- Why it is a real risk.
- The smallest reasonable fix.
- Whether the fix is safe to apply now.

## Fix Loop

Run up to 3 iterations.

For each iteration:

1. Review the target diff.
2. Fix findings that are clear, local, and within scope.
3. Leave design choices, ambiguous requirements, or risky behavior changes for the user instead of guessing.
4. Run the narrowest meaningful verification.
5. Review only the new diff created by the fix.

Stop early when no serious findings remain.

Stop and report instead of continuing when:

- A fix requires product or architecture decisions the user has not made.
- The remaining issue needs external credentials, unavailable services, or large test data.
- Verification requires a destructive operation or broad environment change.
- The same class of issue remains after 3 loops.

## Verification

Choose verification proportional to the change:

- Small pure function change: focused unit test or import/compile check.
- UI change: focused test plus browser or screenshot check when a running app is relevant.
- Streamlit change: compile/import check, focused tests, health check, and browser text check when practical.
- Data/schema/import change: fixture-based test plus output artifact inspection.
- Docs-only change: link/path sanity and rendered structure check when relevant.

Do not run an expensive full suite by default when a focused test proves the edited behavior. Mention when full-suite coverage was skipped.

## Final Answer

Lead with the review outcome, then summarize fixes.

Use this structure:

- **Findings:** serious issues found initially, or "No serious findings remain" after the loop.
- **Fixed:** concrete changes made.
- **Verified:** commands, browser checks, health checks, or artifact checks run.
- **Remaining risk:** skipped tests, accepted limitations, or decisions still needing the user.
- **Next path:** 1-2 useful next actions only when they naturally follow.

If no edits were needed, say that clearly and list any residual test gaps.

## Rules

- Keep fixes narrow and reviewable.
- Do not commit, push, change visibility, or rewrite history unless the user explicitly asks.
- Do not reformat unrelated files.
- Do not revert user changes unless explicitly requested.
- Prefer existing project patterns and test helpers.
- When the user asks for inline code-review comments, emit inline comments for actionable findings; otherwise keep findings in the final response.

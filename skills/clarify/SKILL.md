---
name: clarify
description: "Debt-prevention clarification for ambiguous or high-risk coding work. Use before implementing when a request may create technical debt: unclear acceptance criteria, architecture or data-model changes, persistence/schema changes, broad refactors, new dependencies, user-facing workflow changes, irreversible file/data operations, compliance-sensitive claims, or when the user says they can only judge outcomes and wants help defining what done means. Do not use for clear bug reports, explicit implementation plans, small scoped UI tweaks, continue doing this, or tasks where enough context already exists to proceed safely."
---

# Clarify

Use this skill as a technical-debt gate, not as a generic conversation blocker.

The user often cannot review every implementation detail and mainly validates the final outcome. Protect them by clarifying the decisions that would be expensive to undo, then proceed decisively once the debt risk is bounded.

## Trigger

Trigger when at least one is true:

- Acceptance is unclear: the request says what to build, but not how the user will know it is done.
- Scope can grow silently: the change may touch architecture, shared services, data flow, schema, persistent files, auth, deployment, or cross-project conventions.
- The implementation may add a long-term dependency, new abstraction, background process, hook, automation, generated data format, or migration path.
- The user asks for optimization, refactor, simplification, redesign, or "make it better" without a concrete target.
- The user says they are not sure what happened, can only judge the result, or wants Codex to reduce technical debt.
- The task has safety, compliance, publication, data-loss, or irreversible Git/GitHub risk.

Do not trigger when:

- The user provides a clear bug report, stack trace, failing behavior, or reproduction path. Use diagnosis instead.
- The user gives a concrete plan and says to implement it.
- The user says "继续做", "直接做", "按这个做", or "先做一版".
- The task is a small, reversible UI/text/style tweak with obvious acceptance.
- Prior discussion in the thread already established scope and acceptance.

## Debt Gate

Before coding, identify the smallest missing decision that can prevent debt. Ask at most one question at a time.

Prefer these question types:

- **Outcome:** What should the user be able to see, click, run, or export when this is done?
- **Boundary:** What should stay out of scope for this change?
- **Ownership:** Should this live in the current module/project, a shared helper, a skill, a hook, or documentation?
- **Persistence:** Is this temporary, local-only, repo-tracked, or part of a long-term data/schema/API contract?
- **Verification:** Which focused command, browser check, output file, health check, or manual workflow proves success?
- **Debt budget:** Is a quick version acceptable with a documented follow-up, or should the implementation avoid known shortcuts now?

If the user cannot answer, give 2-3 concrete options and recommend one. Include tradeoffs in one sentence each.

## Proceeding Rule

Proceed without more questions once the following are clear enough:

- Intended user-visible outcome.
- Scope boundary and non-goals.
- Persistence/ownership decision when relevant.
- Focused verification signal.

Do not ask every theoretical question. Ask only what changes the implementation path or prevents debt.

## During Implementation

When using this skill, keep a short debt ledger in the final answer:

- **Done:** user-visible result.
- **Verified:** focused checks run.
- **Debt avoided:** important shortcut or scope trap that was avoided.
- **Remaining debt:** any accepted limitation, follow-up, or risk.

If no code is changed, still give the user an acceptance checklist they can use to judge the outcome.

## Rules

- Ask in Chinese unless the user asks otherwise.
- Keep questions concrete and tied to technical debt.
- Do not block clear execution with ceremony.
- Do not turn clarification into a full design document unless the user explicitly asks for a plan.
- If the user says to proceed, stop asking and implement with the safest reasonable assumptions.

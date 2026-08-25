---
name: streamlit-feature-change
description: Use when adding, removing, renaming, or refactoring Streamlit features, pages, navigation entries, sidebar flows, session_state usage, cached functions, or modules used by Streamlit pages. Also use when a Streamlit app errors because a page still imports or calls an old module after a feature change. Do not use for non-Streamlit apps, pure visual copy tweaks, or bug diagnosis unrelated to page wiring.
---

# Streamlit Feature Change

## Overview

Keep Streamlit feature changes complete across the app surface: entrypoints, `pages/`, navigation, module imports, `st.session_state`, caches, tests, and docs. Prefer adaptable inspection and project-native verification over fixed reusable scripts.

## Workflow

### 1. Classify the change

Identify whether the task is adding, deleting, renaming, moving, or refactoring a feature. If acceptance criteria, destination page, old feature name, or replacement behavior is unclear and the ambiguity affects architecture or data flow, ask before editing.

When enough context exists, proceed directly. Do not stop after proposing a checklist.

### 2. Map the Streamlit surface

Find the app surface before editing:

- Entrypoints such as `streamlit_app.py`, `app.py`, `Home.py`, `main.py`, or launch scripts.
- Multipage files under `pages/`.
- Custom navigation, sidebar menus, routers, page registries, config-driven menus, and links.
- Feature modules imported by pages.
- `st.session_state` keys, cache decorators, resource initializers, query params, and file paths used by the feature.
- Tests, docs, examples, launchers, and saved config that reference the feature.

Use codebase graph tools first when the project has a usable index. Use text search for string literals, page filenames, Streamlit keys, error messages, configs, and docs.

### 3. Edit all affected call sites

For additions:

- Register the new page or feature wherever users navigate to it.
- Wire imports from the intended module path.
- Initialize required `st.session_state` keys safely.
- Prefer existing project patterns for layout, caching, and service calls.

For deletions or renames:

- Remove or update page imports, navigation entries, callbacks, links, tests, docs, and launch references.
- Replace old `st.session_state` keys or provide migration/default handling when existing sessions may hit the code path.
- Clear or rename cache keys only when the project already has a cache invalidation pattern; otherwise avoid broad cache hacks.
- Keep compatibility shims only when they reduce user-facing breakage and are small enough to remove later with a clear note.

### 4. Run layered checks

Prefer project-native commands from `AGENTS.md`, README, Makefile, pyproject, package scripts, or existing CI. If none exist, choose the lightest checks that fit the repo:

- Static search for old feature names, module paths, page filenames, session keys, and menu labels.
- Python compile/import checks for touched modules and page files when import side effects are acceptable.
- Focused tests for the changed feature or navigation.
- Minimal Streamlit startup or health check only when it is cheap and the app can run locally without unavailable services.

Do not invent a permanent smoke script unless the user asks or the repo already has a clear test utility pattern. Inline one-off checks are acceptable during the task.

### 5. Re-review the page call chain

After fixing and verifying, review the new diff specifically for stale Streamlit wiring:

- No page imports a deleted or renamed module.
- No navigation item points to a removed page or dead callback.
- No old session key is required without initialization or migration.
- No cache/resource initializer still references obsolete objects.
- Tests/docs do not claim the removed feature still exists.

Fix clear findings automatically, rerun the focused check, then re-review. Stop after a bounded loop if the remaining issue needs a product decision, external service, credentials, or broad architecture choice.

## Output

Summarize:

- What Streamlit surface was changed.
- Which old references were removed or migrated.
- Which checks ran and their result.
- Any remaining risk, especially unrun app startup, unavailable services, or intentionally retained compatibility shims.

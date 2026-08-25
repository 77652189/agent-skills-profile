# clarify — Claude Code Skill

A Claude Code skill that pauses before implementing any new feature or change, and asks clarifying questions one at a time to understand scope, acceptance criteria, edge cases, and integration.

## What it does

When you propose new work, instead of jumping straight to code, Claude will:

1. Ask one clarifying question at a time (scope, acceptance criteria, edge cases, integration)
2. Help you answer if you're unsure — explaining why the question matters and offering options
3. Summarize its understanding before starting implementation

Say **"enough, let's start"** at any point to skip ahead.

## Why

The most common source of wasted effort is building the wrong thing. This skill enforces a short clarifying loop before any implementation begins — even for requests that seem simple.

## Triggers

Activates automatically when you say things like:

- 我想做X / 能不能加X / 我需要X / 我希望X
- 改一下X / 优化X / 修改X
- "I want to add X", "can we change X", "let's build X"

## Install

```bash
npx skills add 77652189/clarify-skill
```

No restart needed — Claude Code picks up skills automatically.

---
name: best-practice
description: R&D: distils what worked and what was reverted per folder into practices notes.
tools: Read, Grep, Glob, Bash, Edit, Write
model: sonnet
---

Before acting read `.agents/core/rules.md`, `.agents/core/layers.md` and `.agents/profile.toml`. Return at most 30 lines to your caller; put detail in files under `.agents/`.

From `.agents/reports/<folder>/`, `registry.jsonl` and handoffs write `.agents/practices/<folder>.md` (<= 40 lines): tools that paid off, change kinds that merged, kinds that were reverted. Evidence only, from the project's own files.

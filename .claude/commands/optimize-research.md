---
description: R&D: research one topic or prototype it on an agent-rd branch (never merges by itself)
argument-hint: "<topic: one-line question + stopping condition> [--explain]"
---

Argument: `$ARGUMENTS`. Without a clear question and a stopping condition, ask for them and stop.

0. Note the start time first: `date -u +%FT%TZ` (START). The ledger measures this run's tokens from it.
1. Read `.agents/core/rules.md`, `.agents/profile.toml`. Run `python3 .agents/scripts/budget.py check --kind rd`; stop on STOP.
1b. If `.agents/grill/<topic>.md` exists, pass its status to the researcher: `answered` = follow its `## Direction`; `open` = do not run, tell the owner to answer with `/optimize-grill <topic>`.
2. Launch `rd-researcher` for the topic. Findings go to `.agents/research/<topic>.md` (format: see `rd-researcher`). A prototype goes on `agent-rd/<topic>` and is registered with `registry.py add`.
3. When asked, or after a batch of runs, launch `best-practice` to refresh `.agents/practices/<folder>.md`.
4. Log with `ledger.py add --command optimize-research --session current --since <START>`. Report in <= 15 lines. Anything worth doing is proposed as a task for `/optimize-plan`; do not merge it.

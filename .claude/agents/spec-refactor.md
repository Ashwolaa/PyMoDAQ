---
name: spec-refactor
description: Specialist: factorizes duplicated code within one scope.
tools: Read, Grep, Glob, Bash, Edit, Write
model: sonnet
---

Before acting read `.agents/core/rules.md`, `.agents/core/layers.md` and `.agents/profile.toml`. Return at most 30 lines to your caller; put detail in files under `.agents/`.

Factor out duplication named in the task. Keep behaviour identical, keep old names working through shims with `deprecation_msg` when public, run the scope's tests before and after, and stay within the PR line cap.

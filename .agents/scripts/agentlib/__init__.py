"""Shared, tested building blocks of the .agents scripts (standard library only).

  gitx      running git and other commands; `git status --porcelain` parsed without losing the first column
  plans     plan files: task blocks, fields, statuses, the package a task belongs to
  reports   pr-reviewer reports: header lines, summary, notes outside the change
  evidence  what a session really did, read from its transcripts (sub-agent launches, file edits)
State files and the profile stay in `_common.py` (load_toml, read_jsonl, fail, require_state_branch, ...).
Tests: `.agents/tests/` (`pytest .agents/tests` under the profile's [tools].env).
"""

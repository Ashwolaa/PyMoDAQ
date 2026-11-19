# Formats

## registry.jsonl (one JSON object per line, append via `scripts/registry.py`)
`run_id, date, scope, specialty, branch, pr (int|null), status (pushed|open|merged|reverted|closed), risk (low|medium|high), task_id`
`pushed` = branch pushed with CI run by `scripts/ci.py`, no PR yet; `open` = PR opened by /optimize-merge (or an old draft).

## findings.jsonl (via `scripts/findings.py`)
`key, scope, kind (ci-upstream|review|run), title, evidence [urls], sources [run ids], first_seen, last_seen, seen,
status (open|planned|closed), task_id, note`. Problems found outside the scans; the same key is recorded once
(`seen` counts repeats). `/optimize-plan` gives the open ones of its scope to triage and the decisioners.

## ledger.jsonl (append via `scripts/ledger.py add`)
`run_id, date, command, scope, mode (explain|run), model_tier, tokens_in, tokens_out, specialist_runs, prs_opened, reviews,
outcome (ok|failed|limit|budget), note`, plus, when logged with `--session current --since <START>`: `session_id,
started, ended, minutes, tokens_cache_read, requests, tool_calls, out_by_agent` (output tokens per agent type).
`tokens_in` = uncached input + cache writes. Figures are measured by `scripts/usage.py` from the local transcripts
(main session and its sub-agents); write `null` if unknown (e.g. cloud runs), never guess.

## Plan quota
Not readable as a number by a session. `usage.py snapshots` lists the `/usage` readings (session %, week %, reset
times) and limit hits found in the transcripts; `usage.py calibrate` turns two readings of the same weekly window
into tokens per week-%. Budget caps in `budget.toml` are set from these figures, not from guesses.

## scans/<scope>-<tree>.md (written by `scripts/scan.py`)
Header (scope, path, git tree id of the scanned folder, tool versions), then ruff (bug risk, unused imports and
simplifications listed with `path:line`; style counted per rule), vulture (>= 80% listed, lower counted per file),
radon (rank C or worse), jscpd (duplicate pairs). Footer: sha256 of the content. Same tree + same tool versions =
same file, so two runs can be shown to have had identical input. Advisors read this file and nothing else.

## Run ids
`<date>-run-<task-id>` for /optimize-run (one per task), `<date>-plan-<scope>` for /optimize-plan,
`<date>-merge-<scope|task-id|all>` for /optimize-merge, `<date>-<command>-<topic>` for the others. Experiments may append a suffix (`-A2-haiku`).

## plans/<date>-<scope>.md
Header (scope, base commit, date) then one block per task:
`id, title, scope, specialty, risk, files (path:line), verdicts (decider: approve|veto + 1 line), status`
Status: proposed | approved | done | blocked | expired (14 days). References must be re-checked against the
current head before execution.

## handoff/<package>.md (overwritten each run, max 40 lines)
Sections in this order: Done, Open findings (ranked, `path:line`, risk), Blocked, Next step (one action), Evidence
(test results, coverage diff, screenshot paths). The next run reads this file first.

## reports/<folder>/<date>-<kind>.md
Kinds: run, audit, review (committee), merge, `pr-review-<task-id>` (pr-reviewer; first four lines `verdict:`,
`public_api:`, `behaviour_change:`, `fails_without_fix:`, read by `scripts/merge_gate.py`). Short, factual, numbers from files.

## practices/<folder>.md
What worked / was reverted in that folder, written by best-practice; read by specialists before they start.

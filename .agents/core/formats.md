# Formats

## registry.jsonl (one JSON object per line, append via `scripts/registry.py`)
`run_id, date, scope, specialty, branch, pr (int|null), status (open|merged|reverted|closed), risk (low|medium|high), task_id`

## ledger.jsonl (append via `scripts/ledger.py add`)
`run_id, date, command, scope, mode (explain|run), model_tier, tokens_in, tokens_out, specialist_runs, prs_opened,
outcome (ok|failed|limit|budget), note`. Token figures come from the session; write `null` if unknown, never guess.

## plans/<date>-<scope>.md
Header (scope, base commit, date) then one block per task:
`id, title, scope, specialty, risk, files (path:line), verdicts (decider: approve|veto + 1 line), status`
Status: proposed | approved | done | blocked | expired (14 days). References must be re-checked against the
current head before execution.

## handoff/<package>.md (overwritten each run, max 40 lines)
Sections in this order: Done, Open findings (ranked, `path:line`, risk), Blocked, Next step (one action), Evidence
(test results, coverage diff, screenshot paths). The next run reads this file first.

## reports/<folder>/<date>-<kind>.md
Kinds: run, audit, review. Short, factual, numbers from files.

## practices/<folder>.md
What worked / was reverted in that folder, written by best-practice; read by specialists before they start.

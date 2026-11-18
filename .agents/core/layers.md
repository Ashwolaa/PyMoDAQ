# Layers and roles

Execution is flat: the main session plays the coordinator, adopts a co-coordinator role per scope, and
launches specialists as sub-agents. Sub-agents are not assumed to be able to spawn sub-agents.

| Layer | Writes code? | Agents |
|---|---|---|
| Advisory board | no (writes plans only) | advisor-quality, advisor-uxui, advisor-performance, advisor-docs, advisor-compat -> decider-triage; decider-compat-risk, decider-test-change, decider-arbiter |
| Executive | yes, on agent branches | cocoordinator (role per scope), spec-hygiene, spec-test-quality, spec-refactor, spec-uiux, spec-docs, test-agent (one instance per test folder) |
| Audit | no | auditor + scripted checks |
| R&D | prototypes on `agent-rd/*` only | rd-researcher, best-practice |
| Committee | no | committee-efficiency, committee-outcomes, committee-governance |

## Deliberation (advisory board)
1. Scanners (tools, not LLMs) produce ranked findings. Advisors read only that output and give short opinions.
2. decider-triage ranks findings and keeps those worth a task.
3. Two decisioners review each kept finding independently: always decider-compat-risk, plus decider-test-change
   for anything touching tests, else decider-triage's second opinion by a fresh instance.
4. Both approve -> task `approved` if low risk, else `proposed`. Any veto -> blocked.
5. On disagreement each reads the other's reasoning and decides again. Still split -> `blocked`, listed for the human.
6. decider-arbiter settles two tasks that change the same file; its ruling is binding.

## Committee
Independent: reads only `ledger.jsonl`, `registry.jsonl`, `handoff/`, `reports/`, audit blocks; never source.
Cannot be consulted by coordinators. May recommend changes and pause a role (human confirms). Never edits
`.claude/agents/` or `.claude/commands/` — such changes are `proposed` tasks.

## Model tiers
Scanning/summarising: haiku. Specialists and advisors: sonnet. Decisioners, committee, API-touching edits: the strongest model.

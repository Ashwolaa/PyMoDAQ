# Layers and roles

Execution is flat: the main session plays the coordinator, adopts a co-coordinator role per scope, and
launches specialists as sub-agents. Sub-agents are not assumed to be able to spawn sub-agents.

| Layer | Writes code? | Agents |
|---|---|---|
| Advisory board | no (writes plans only) | advisor-quality, advisor-uxui, advisor-performance, advisor-docs, advisor-compat -> decider-triage; decider-compat-risk, decider-test-change, decider-arbiter |
| Executive | yes, on agent branches | cocoordinator (role per scope), spec-hygiene, spec-test-quality, spec-refactor, spec-uiux, spec-docs, test-agent (one instance per test folder) |
| Audit | no | scripted checks (`merge_gate.py lint` before each push, `ci.py`, `merge_gate.py check`); pr-reviewer validates each branch (task match, drift, correctness) before /optimize-merge opens its PR |
| R&D | prototypes on `agent-rd/*` only | rd-researcher, best-practice; plugins (`/optimize-plugins`): plugin-scout (read-only), spec-plugin-port (ports on the owner's fork only) |
| Committee | no | committee (one agent, three parts: efficiency, outcomes, governance) |

## Deliberation (advisory board)
1. Scanners (tools, not LLMs) produce ranked findings. Advisors read only that output and give short opinions.
2. decider-triage ranks findings and keeps those worth a task.
3. Two decisioners review each kept finding independently: always decider-compat-risk, plus decider-test-change
   for anything touching tests, else decider-triage's second opinion by a fresh instance.
4. Both approve -> task `approved` if low risk, else `proposed`. Any veto -> blocked.
5. On disagreement each reads the other's reasoning and decides again. Still split -> `blocked`, listed for the human.
6. decider-arbiter settles two tasks that change the same file; its ruling is binding.

## Committee
Independent: reads only `ledger.jsonl`, `registry.jsonl`, `findings.jsonl`, `handoff/`, `reports/`; never source.
Cannot be consulted by coordinators. May recommend changes and pause a role (human confirms). Never edits
`.claude/agents/` or `.claude/commands/` — such changes are `proposed` tasks.

## Model tiers
Set from experiments A2, A3 and B (2026-11-19, `pymodaq_utils`, identical scan input): advisors haiku (same core findings,
slightly cheaper in quota); decider-triage, decider-test-change, decider-arbiter sonnet (about 10-20% cheaper per run, vetoes held);
decider-compat-risk the strongest model (the one Sonnet slip was approving a public-API change). Specialists sonnet;
committee, pr-reviewer (last check before code lands, owner's choice 2026-11-19) and API-touching edits the strongest model.
The auditor agent was removed on 2026-11-19 (owner): in 7 runs it reported "no drift" each time and once read the wrong
repo; its compliance checks are now `merge_gate.py lint`, its drift check is part of pr-reviewer. Re-check these with the ledger before changing them.

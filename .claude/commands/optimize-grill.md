---
description: Grill the owner on a pending request: ask the questions an agent left, record the answers
argument-hint: "[topic]"
---

Run in an interactive session. Argument: `$ARGUMENTS` (a topic from `python3 .agents/scripts/grill.py list --status open`; empty = list them and ask which).

1. Read `.agents/grill/<topic>.md`: the `## Decision` section and the numbered questions, each with the agent's recommended answer and evidence.
2. Interview the owner one question at a time, most decisive first. For each, state the recommended answer and why, and let the owner accept, change or reject it. Follow a surprising answer with the question it raises, even if the file did not list it. Stop early when the decision is clear; skip questions an earlier answer made moot.
3. Write the answers into the same file under `## Answers` (question number, answer, date, one line of the owner's reasoning), plus a `## Direction` paragraph: what the agents now build or research, and what is ruled out.
4. `python3 .agents/scripts/grill.py answer --topic <topic>` (or `--status dropped` if the owner says the question no longer matters), then `git add .agents && git commit -m "Owner answers grill <topic> [skip ci]" && git push origin dev_agent`.
5. Say which command picks it up next (`/optimize-research` or `/optimize-plan <scope>`), which read `## Direction` as a constraint.

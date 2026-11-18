# optimize-plan pymodaq_utils --explain (2026-11-19)

Budget: GO (runs 0/1). Pilot mode = explain, so no plan written.

## Scanners
All missing in this environment: ruff, vulture, jscpd, radon, coverage, mutmut (not on PATH, not importable
from python3). `python` is also absent (only `python3`), so the command text `python .agents/scripts/...` fails as written.

## Outcome
No scan output, so advisors and decisioners were NOT launched (rule: report missing scanners, never imitate them).
No findings, no tasks.

## Scope facts (verified)
pymodaq_utils/src: ~7.2k lines; largest files utils.py (959), plugin_tools/rules.py (845), plugin_tools/checks.py (690),
math_utils.py (645), config.py (623).

## Needed from the human
Install scanners, e.g. `pip install ruff vulture radon coverage` (+ `npm i -g jscpd`), then rerun.

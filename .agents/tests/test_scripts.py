"""The scripts' decision logic: merge gate, budget kinds, CI triggers, cost check, the upstream guard."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1]
REPO = AGENTS.parent


def script(*args, **kw):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=REPO, **kw)


# ---------------------------------------------------------------- merge_gate
def test_approving_deciders():
    import merge_gate
    two, veto = merge_gate.approving_deciders("decider-compat-risk and decider-triage: approve in round 2 (pilot)")
    assert two == {"decider-compat-risk", "decider-triage"} and not veto
    one, _ = merge_gate.approving_deciders("approved in all 8 runs (compat-risk and a second decisioner each time)")
    assert one == {"decider-compat-risk"}
    _, veto = merge_gate.approving_deciders("decider-compat-risk: approve; A2-haiku: blocked, owner decides")
    assert veto


@pytest.mark.parametrize("path,expected", [("packages/pymodaq_utils/tests/utils_test.py", True),
                                           ("packages/x/src/test_helpers.py", True),
                                           ("packages/pymodaq_utils/src/pymodaq_utils/utils.py", False)])
def test_is_test(path, expected):
    import merge_gate
    assert merge_gate.is_test(path) is expected


# ---------------------------------------------------------------- budget
@pytest.mark.parametrize("kind", ["executive", "rd", "merge", "pr"])
def test_budget_kinds_do_not_crash(kind):
    """7357fd0ce, 2026-11-19: a comment swallowed the 'merge' entry, `--kind merge` raised KeyError."""
    r = script(str(AGENTS / "scripts" / "budget.py"), "check", "--kind", kind)
    assert r.returncode in (0, 1), r.stderr
    assert "Traceback" not in r.stderr


# ---------------------------------------------------------------- ci
def test_ci_triggers_and_scopes():
    import ci
    utils = ci.triggers((REPO / ".github/workflows/tests-utils.yml").read_text())
    assert "workflow_dispatch" in utils and "packages/pymodaq_utils/**" in utils["pull_request"]
    doc = ci.triggers((REPO / ".github/workflows/compile-doc.yml").read_text())
    assert doc["pull_request"] is None  # no paths filter: runs on every PR
    assert ci.scope_of("tests-pymodaq.yml") == "pymodaq"
    assert ci.loose("tests (ubuntu-latest, 3.12, pyside6)") == "tests (ubuntu-latest, pyside6)"


# ---------------------------------------------------------------- cost
def test_cost_fits(tmp_path, monkeypatch):
    import cost
    monkeypatch.setattr(cost, "store", lambda: tmp_path / "costs.jsonl")
    s, w, src = cost.estimate("plan")
    assert (s, w, src) == (18.0, 2.0, "seed")
    for d in (2, 3, 4):
        with open(tmp_path / "costs.jsonl", "a") as f:
            f.write(json.dumps({"kind": "merge", "units": 1, "session": d, "week": 0}) + "\n")
    s, w, src = cost.estimate("merge", units=2)
    assert s == 6.0 and src.startswith("median of 3")


# ---------------------------------------------------------------- upstream guard hook
@pytest.mark.parametrize("cmd,blocked", [
    ("ls", False),
    ("git push origin dev_agent", False),
    ("git push --force-with-lease origin agent/pymodaq_utils/docs/2026-11-19", False),
    ("gh pr view 3 -R Ashwolaa/PyMoDAQ", False),
    ("git push upstream dev", True),
    ("cd x && git push origin upstream/dev:refs/heads/dev", True),
    ("git push origin dev", True),
    ("gh pr list -R PyMoDAQ/PyMoDAQ", True),
    ("gh run list --repo=PyMoDAQ/PyMoDAQ", True),
    ("gh pr create -R Ashwolaa/PyMoDAQ --base dev_agent", True),
    ("gh pr merge 5 -R Ashwolaa/PyMoDAQ --merge", True),
    ("gh api repos/PyMoDAQ/PyMoDAQ/issues -X POST -f title=x", True),
])
def test_guard_upstream(cmd, blocked):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    r = script(str(REPO / ".claude/hooks/guard_upstream.py"), input=payload, env={"CLAUDE_PROJECT_DIR": str(REPO),
                                                                                 "PATH": "/usr/bin:/bin"})
    assert (r.returncode == 2) is blocked, (cmd, r.stderr)


# ---------------------------------------------------------------- status
def test_status_next_is_a_known_step():
    r = script(str(AGENTS / "scripts" / "status.py"), "next")
    assert r.returncode == 0 and r.stdout.split()[0] in ("merge", "run", "plan", "review", "idle")

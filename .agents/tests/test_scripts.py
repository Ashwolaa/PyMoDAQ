"""The scripts' decision logic: merge gate, budget kinds, CI triggers, cost check, the upstream guard."""
import json
import os
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


# ---------------------------------------------------------------- docs
def test_commands_page_is_current():
    """COMMANDS.md is generated from the commands, agents and scripts; regenerate it after changing any of them."""
    r = script(str(AGENTS / "scripts" / "docs.py"), "--check")
    assert r.returncode == 0, r.stdout


# ---------------------------------------------------------------- grill
GOOD = "## Decision\nWhich API?\n\n1. A or B?\n   Recommended: A (evidence)\n2. Keep X?\n   Recommended: yes\n3. Scope?\n   Recommended: small\n"


def test_grill_file_check():
    import grill
    assert grill.check_file(GOOD) == []
    assert any("Decision" in p for p in grill.check_file(GOOD.replace("## Decision", "## Why")))
    assert any("numbered" in p for p in grill.check_file("## Decision\nx\n1. only one\n   Recommended: a\n"))
    assert any("Recommended" in p for p in grill.check_file(GOOD.replace("   Recommended: yes\n", "")))


def test_grill_add_cap_and_answer(tmp_path, monkeypatch):
    import grill
    monkeypatch.setattr(grill, "AGENTS_DIR", tmp_path)
    monkeypatch.setattr(grill, "read_jsonl", lambda name: [json.loads(l) for l in (tmp_path / name).read_text().splitlines()]
                        if (tmp_path / name).exists() else [])
    monkeypatch.setattr(grill, "require_state_branch", lambda: None)
    monkeypatch.setattr(grill, "max_open", lambda: 1)
    (tmp_path / "t.md").write_text(GOOD)
    ns = lambda **k: type("A", (), {"scope": "s", "file": str(tmp_path / "t.md"), "source": None, **k})
    grill.cmd_add(ns(topic="one"))
    grill.cmd_add(ns(topic="one"))  # already open: no second row
    assert len(grill.read_jsonl("grill.jsonl")) == 1
    with pytest.raises(SystemExit) as e:
        grill.cmd_add(ns(topic="two"))
    assert e.value.code == 3  # cap reached
    grill.cmd_answer(type("A", (), {"topic": "one", "status": "answered"}))
    assert grill.read_jsonl("grill.jsonl")[0]["status"] == "answered"
    grill.cmd_add(ns(topic="two"))  # room again


# ---------------------------------------------------------------- status: pending
def test_pending_skips_branches_blocked_by_review(monkeypatch):
    """2026-11-22: a pushed branch whose task was blocked by its review made the cycle pick `merge` for ever
    ('merge again, no progress') while the rework was never run."""
    import status
    rows = [{"status": "pushed", "task_id": "T-a", "branch": "b-a"}, {"status": "pushed", "task_id": "T-b", "branch": "b-b"},
            {"status": "pushed", "task_id": "T-c", "branch": "b-c"}, {"status": "merged", "task_id": "T-d", "branch": "b-d"}]
    monkeypatch.setattr(status, "read_jsonl", lambda name: rows)
    monkeypatch.setattr(status, "tasks", lambda: [("T-a", "", "done — branch b-a, CI green, awaiting review", "", "x"),
                                                  ("T-b", "", "blocked — review: changes", "", "x"),
                                                  ("T-c", "", "blocked — CI red", "", "x")])
    assert [r["task_id"] for r in status.pending()] == ["T-a", "T-c"]


# ---- task.py checks: a test run never hangs an agent, never touches the real HOME
def _fake_profile(tmp_path, **checks):
    return {"tools": {"env": ""}, "checks": {
        "test": f"cd {tmp_path} && {sys.executable} -m pytest", "qt_backend_env": "X_BACKEND={backend}",
        "qt_headless": "", **checks}}


def test_run_tests_kills_a_hung_test_and_dumps_its_stack(tmp_path, monkeypatch):
    import task
    (tmp_path / "test_hang.py").write_text("import time\n\ndef test_hang():\n    time.sleep(60)\n")
    monkeypatch.setattr(task, "profile", lambda: _fake_profile(tmp_path, test_timeout_s=4, test_faulthandler_s=1))
    r, timed_out = task.run_tests("pyqt6", "x")
    assert timed_out
    assert "test_hang" in task.dump_of(r.stdout + r.stderr)


def test_run_tests_uses_a_throwaway_home(tmp_path, monkeypatch):
    import task
    (tmp_path / "test_home.py").write_text(
        "import os, pathlib\n\ndef test_home():\n    pathlib.Path(%r).write_text(os.environ['HOME'] + '|' + os.environ['USERPROFILE'])\n"
        % str(tmp_path / "seen.txt"))
    monkeypatch.setattr(task, "profile", lambda: _fake_profile(tmp_path))
    r, timed_out = task.run_tests("pyqt6", "x")
    home, userprofile = (tmp_path / "seen.txt").read_text().split("|")
    assert r.returncode == 0 and not timed_out
    assert home == userprofile and home != os.environ["HOME"] and not Path(home).exists()  # removed afterwards


def test_a_pr_without_checks_yet_is_retried_by_merge_not_run():
    import merge, status
    assert "blocked — PR CI unavailable" in merge.RETRY
    assert "blocked — PR CI unavailable" in status.MERGE_RETRY
    assert "blocked — PR CI unavailable" not in status.RETRY  # /optimize-run must not take it as a fresh task


@pytest.mark.parametrize("changed, errors", [
    ([".agents/scripts/scan.py", ".agents/tests/test_scripts.py", ".agents/COMMANDS.md"], []),
    ([".agents/scripts/scan.py", "packages/pymodaq_gui/src/x.py"], ["packages/pymodaq_gui/src/x.py"]),
    ([".agents/ledger.jsonl", ".agents/plans/p.md"], [".agents/ledger.jsonl", ".agents/plans/p.md"]),
    ([".claude/agents/spec-tool.md"], [".claude/agents/spec-tool.md"]),
])
def test_tool_branch_carries_tool_code_only(changed, errors):
    import merge_gate
    assert merge_gate.is_tool_branch("agent-tool/T-pymodaq_gui-004")
    assert not merge_gate.is_tool_branch("agent/pymodaq_gui/tool/2026-11-26")
    assert merge_gate.tool_path_errors(changed) == errors


def test_tool_branch_auto_merges_only_outside_the_guards():
    import merge_gate
    scan = [".agents/scripts/scan.py", ".agents/tests/test_scripts.py"]
    assert merge_gate.tool_human_reasons(scan, [("3", "1", scan[0]), ("12", "0", scan[1])]) == []
    gate = [".agents/scripts/merge_gate.py"]
    assert "guards" in merge_gate.tool_human_reasons(gate, [("2", "2", gate[0])])[0]
    assert "removes lines" in merge_gate.tool_human_reasons(scan, [("3", "1", scan[0]), ("0", "4", scan[1])])[0]

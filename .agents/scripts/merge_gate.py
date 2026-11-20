#!/usr/bin/env python3
"""Decide whether a reviewed agent branch may merge into dev_agent without the human. Usage:

  merge_gate.py lint --branch B [--task-id T] [--base dev_agent]
      compliance only (branch name, product files only, Agent-Run trailers naming the task, size cap, registry):
      exit 0 = ok, 1 = violations listed. Run before pushing a task branch; `check` runs it too.
  merge_gate.py check --branch B --plan P --task-id T --review R [--base dev_agent]
      exit 0 = AUTO-MERGE, exit 1 = HUMAN (reasons printed), exit 2 = error / not mergeable at all

Rule (BRIEFING): low-risk tasks that two decisioners both approved may auto-merge; anything touching tests, UI or
public API waits for the human. Concretely AUTO-MERGE needs all of:
  - registry risk and plan risk are `low`;
  - the plan's verdicts name at least two different deciders approving, and no veto/blocked;
  - the pr-reviewer report says `verdict: approve` and `public_api: no`;
  - no changed file is a test, none is in a `[scopes].ui` package, the diff is within `[limits].pr_max_changed_lines`.
A lint violation (see `lint`), or a review verdict other than approve, is an error (exit 2).
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, load_toml, read_jsonl
from registry import BRANCH_RE
from agentlib import gitx, plans, reports

REPO_ROOT = AGENTS_DIR.parent


def git(*args: str) -> str:
    return gitx.git(*args)


def task_block(plan, task_id: str) -> str:
    task = plans.find(task_id, plan)
    if not task:
        fail(f"{task_id} not found in {plan}")
    return task.block


def approving_deciders(verdicts: str) -> tuple[set, bool]:
    """Deciders that approve, and whether any segment vetoes or blocks."""
    approve, veto = set(), False
    for seg in re.split(r";", verdicts):
        names = {f"decider-{n}" for n in re.findall(r"(?:decider-)?\b(compat-risk|triage|test-change|arbiter)\b", seg)}
        low = seg.lower()
        if re.search(r"\bveto|\bblocked\b", low):
            veto = True
        elif "approve" in low:
            approve |= names
    return approve, veto


def review_fields(path) -> dict:
    return reports.header(path)


def is_test(path: str) -> bool:
    name = Path(path).name
    return "/tests/" in f"/{path}" or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def lint(branch: str, base: str, task_id: str | None = None) -> tuple[list, int]:
    """Compliance of a task branch (rules.md 3, 4, 12): what the auditor used to check by hand.
    Returns (violations, changed lines)."""
    profile = load_toml("profile.toml")
    errors = []
    if not BRANCH_RE.match(branch):
        errors.append(f"branch name {branch} does not follow agent/<scope>/<specialty>/<date>[-<topic>]")
    changed = [p for p in git("diff", "--name-only", f"{base}...{branch}").splitlines() if p]
    if not changed:
        errors.append(f"no changes against {base}")
    state = [p for p in changed if p.startswith((".agents/", ".claude/"))]
    if state:
        errors.append(f"state/tooling files on the branch (rules.md 12): {', '.join(state)}")
    for sha in git("rev-list", f"{base}..{branch}").split():
        body = git("log", "-1", "--format=%B", sha)
        m = re.search(r"^Agent-Run:\s*(\S+)", body, re.M)
        if not m:
            errors.append(f"commit {sha[:9]} has no Agent-Run trailer")
        elif task_id and task_id not in m.group(1) and not re.search(rf"\b{re.escape(task_id.rsplit('-', 1)[-1])}\b", m.group(1)):
            errors.append(f"commit {sha[:9]}: Agent-Run {m.group(1)} does not name {task_id}")
    numstat = git("diff", "--numstat", f"{base}...{branch}").splitlines()
    size = sum(int(x) + int(y) for x, y, _ in (l.split("\t", 2) for l in numstat) if x.isdigit() and y.isdigit())
    cap = profile["limits"]["pr_max_changed_lines"]
    if size > cap:
        errors.append(f"{size} changed lines > cap {cap} (rules.md 4)")
    if task_id:
        rows = [r for r in read_jsonl("registry.jsonl") if r["branch"] == branch]
        if rows and rows[-1].get("task_id") not in (None, task_id):
            errors.append(f"registry says {branch} is {rows[-1]['task_id']}, not {task_id}")
    return errors, size


def cmd_lint(a):
    errors, size = lint(a.branch, a.base, a.task_id)
    if errors:
        print("LINT FAILED:\n  " + "\n  ".join(errors))
        sys.exit(1)
    print(f"LINT OK: {a.branch}, {size} changed lines, product files only, trailers present")


def cmd_check(a):
    profile = load_toml("profile.toml")
    reasons = []

    rows = [r for r in read_jsonl("registry.jsonl") if r["branch"] == a.branch]
    if not rows:
        fail(f"{a.branch} is not in registry.jsonl")
    if rows[-1]["risk"] != "low":
        reasons.append(f"registry risk is {rows[-1]['risk']}")

    block = task_block(Path(a.plan) if Path(a.plan).is_absolute() else REPO_ROOT / a.plan, a.task_id)
    risk = re.search(r"\brisk:\s*(\w+)", block)
    if not risk or risk.group(1) != "low":
        reasons.append(f"plan risk is {risk.group(1) if risk else 'missing'}")
    verdicts = re.search(r"^- verdicts:\s*(.*)$", block, re.M)
    approve, veto = approving_deciders(verdicts.group(1) if verdicts else "")
    if veto:
        reasons.append("a decider vetoed or blocked it in the plan")
    if len(approve) < 2:
        reasons.append(f"plan shows {len(approve)} approving decider(s), 2 needed")

    review = review_fields(Path(a.review))
    if review.get("verdict") != "approve":
        fail(f"review verdict is {review.get('verdict', 'missing')}: not mergeable")
    if review.get("public_api") != "no":
        reasons.append(f"reviewer: public_api {review.get('public_api', 'missing')}")

    errors, size = lint(a.branch, a.base, a.task_id)
    if errors:
        fail("not mergeable, lint failed: " + "; ".join(errors))
    changed = [p for p in git("diff", "--name-only", f"{a.base}...{a.branch}").splitlines() if p]
    tests = [p for p in changed if is_test(p)]
    if tests:
        reasons.append(f"touches tests: {', '.join(tests)}")
    root = profile["scopes"].get("root", "packages")
    ui = [p for p in changed if any(p.startswith(f"{root}/{s}/") for s in profile["scopes"].get("ui", []))]
    if ui:
        reasons.append(f"touches a UI scope: {', '.join(ui)}")

    if reasons:
        print("HUMAN: " + "; ".join(reasons))
        sys.exit(1)
    print(f"AUTO-MERGE: low risk, approved by {', '.join(sorted(approve))}, reviewer approve, {size} lines, no tests/UI/API")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    for name in ("branch", "plan", "task-id", "review"):
        c.add_argument(f"--{name}", required=True)
    c.add_argument("--base", default="dev_agent")
    c.set_defaults(fn=cmd_check)
    li = sub.add_parser("lint", help="compliance only: run before pushing a task branch")
    li.add_argument("--branch", required=True)
    li.add_argument("--task-id", default=None)
    li.add_argument("--base", default="dev_agent")
    li.set_defaults(fn=cmd_lint)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

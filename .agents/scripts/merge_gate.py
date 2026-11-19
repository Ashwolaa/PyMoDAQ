#!/usr/bin/env python3
"""Decide whether a reviewed agent branch may merge into dev_agent without the human. Usage:

  merge_gate.py check --branch B --plan P --task-id T --review R [--base dev_agent]
      exit 0 = AUTO-MERGE, exit 1 = HUMAN (reasons printed), exit 2 = error / not mergeable at all

Rule (BRIEFING): low-risk tasks that two decisioners both approved may auto-merge; anything touching tests, UI or
public API waits for the human. Concretely AUTO-MERGE needs all of:
  - registry risk and plan risk are `low`;
  - the plan's verdicts name at least two different deciders approving, and no veto/blocked;
  - the pr-reviewer report says `verdict: approve` and `public_api: no`;
  - no changed file is a test, none is in a `[scopes].ui` package, the diff is within `[limits].pr_max_changed_lines`.
A changed file under `.agents/` or `.claude/`, or a review verdict other than approve, is an error (exit 2).
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, load_toml, read_jsonl

REPO_ROOT = AGENTS_DIR.parent


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO_ROOT)
    if r.returncode:
        fail(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def task_block(plan: Path, task_id: str) -> str:
    text = plan.read_text()
    m = re.search(rf"^## {re.escape(task_id)}\b.*?(?=^## |\Z)", text, re.M | re.S)
    if not m:
        fail(f"{task_id} not found in {plan}")
    return m.group(0)


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


def review_fields(path: Path) -> dict:
    fields = {}
    for line in path.read_text().splitlines()[:12]:
        m = re.match(r"^\s*([a-z_]+):\s*(\S+)", line)
        if m:
            fields.setdefault(m.group(1), m.group(2).lower().strip("`*"))
    return fields


def is_test(path: str) -> bool:
    name = Path(path).name
    return "/tests/" in f"/{path}" or name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


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

    changed = [p for p in git("diff", "--name-only", f"{a.base}...{a.branch}").splitlines() if p]
    state = [p for p in changed if p.startswith((".agents/", ".claude/"))]
    if state:
        fail(f"the branch carries state/tooling files: {', '.join(state)}")
    tests = [p for p in changed if is_test(p)]
    if tests:
        reasons.append(f"touches tests: {', '.join(tests)}")
    root = profile["scopes"].get("root", "packages")
    ui = [p for p in changed if any(p.startswith(f"{root}/{s}/") for s in profile["scopes"].get("ui", []))]
    if ui:
        reasons.append(f"touches a UI scope: {', '.join(ui)}")
    numstat = git("diff", "--numstat", f"{a.base}...{a.branch}").splitlines()
    size = sum(int(x) + int(y) for x, y, _ in (l.split("\t", 2) for l in numstat) if x.isdigit() and y.isdigit())
    cap = profile["limits"]["pr_max_changed_lines"]
    if size > cap:
        reasons.append(f"{size} changed lines > cap {cap}")

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
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

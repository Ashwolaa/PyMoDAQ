#!/usr/bin/env python3
"""/optimize-merge, one candidate at a time. The script does every step except the review itself, and checks that the
review really happened (rules.md 16). Usage, in this order:

  merge.py sync                          registry `open` rows whose PR the human merged/closed -> merged/closed
  merge.py candidates [FILTER]           branches waiting: `<branch> <task-id> <plan> <pr|->`, oldest first
                                         (FILTER = scope or task id)
  merge.py start --branch B              on dev_agent: record the run, rebase B on dev_agent (conflict -> task
                                         blocked), push it if the head changed; prints the run id and the review
                                         report path to give pr-reviewer
  task.py checks RUN [--backend B]       only when start says the rebase changed the head (same run record)
  merge.py ci RUN                        optional: CI on the branch before the review (the normal CI run is the PR's
                                         checks, waited for by gate); exit 2 = again
  (launch pr-reviewer with the task id, plan, branch and the report path; for round > 1 also the previous report)
  merge.py decide RUN                    verifies the review (pr-reviewer launched in this session after start, report
                                         written after start, head unchanged); changes/reject -> plan + registry;
                                         approve -> opens the PR (or marks the old draft ready) with a generated body
  merge.py gate RUN                      waits for the PR's checks (exit 2 = again), runs merge_gate.py check:
                                         AUTO-MERGE -> gh pr merge --merge + pull; HUMAN -> PR left open for the owner
  merge.py close RUN                     ledger line, STATUS.md, commit and push dev_agent
Run records share <git common dir>/agent-runs/ with task.py.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, read_jsonl, today
import task as T
import usage
from agentlib import evidence as ev, gitx, plans, reports
from datetime import datetime, timezone

REPO = AGENTS_DIR.parent
RETRY = ("blocked — CI red", "blocked — PR CI red", "blocked — conflicts")


def fork():
    return T.profile()["project"]["fork"]


def gh_json(*args):
    r = T.sh(["gh", *args, "-R", fork()], check=False)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def plan_of(task_id):
    task = plans.find(task_id)
    return task.plan_rel if task else None


def plan_status(plan, task_id):
    task = plans.find(task_id, plan)
    return task.status if task else ""


def set_status(rec, text):
    T.script("plan.py", "set-status", rec["plan"], rec["task_id"], text)
    rec["outcome_status"] = text


# ------------------------------------------------------------------ sync / candidates
def cmd_sync(a):
    T.clean_on("dev_agent")
    for r in read_jsonl("registry.jsonl"):
        if r["status"] != "open" or not r.get("pr"):
            continue
        pr = gh_json("pr", "view", str(r["pr"]), "--json", "state,isDraft")
        if not pr or pr["state"] == "OPEN":
            continue
        new = "merged" if pr["state"] == "MERGED" else "closed"
        T.script("registry.py", "set-status", "--branch", r["branch"], "--status", new)
        plan = plan_of(r["task_id"]) if r.get("task_id") else None
        if plan and new == "merged" and not plan_status(plan, r["task_id"]).startswith("done — PR"):
            T.script("plan.py", "set-status", plan, r["task_id"], f"done — PR #{r['pr']} merged by the human")
        print(f"sync: #{r['pr']} {r['branch']} -> {new}")


def candidates(filt=None):
    out = []
    for r in read_jsonl("registry.jsonl"):
        if not r.get("task_id") or (filt and filt not in (r["task_id"], r["scope"])):
            continue
        if r["status"] == "pushed":
            pr = None
        elif r["status"] == "open" and r.get("pr"):
            info = gh_json("pr", "view", str(r["pr"]), "--json", "isDraft,state")
            if not info or info["state"] != "OPEN" or not info["isDraft"]:
                continue
            pr = r["pr"]
        else:
            continue
        plan = plan_of(r["task_id"])
        if not plan:
            continue
        st = plan_status(plan, r["task_id"])
        if st.startswith("blocked") and not st.startswith(RETRY):
            continue  # blocked by review -> rework by /optimize-run first; other blocks wait for the human
        out.append((r["branch"], r["task_id"], plan, pr))
    return out


def cmd_candidates(a):
    for b, t, p, pr in candidates(a.filter):
        print(b, t, p, pr or "-")


# ------------------------------------------------------------------ start / ci
def cmd_start(a):
    T.clean_on("dev_agent")
    T.script("budget.py", "check", "--kind", "merge")
    import os
    session = os.environ.get("CLAUDE_CODE_SESSION_ID") or fail("CLAUDE_CODE_SESSION_ID is not set: run from the coordinator's session")
    match = [c for c in candidates() if c[0] == a.branch]
    if not match:
        fail(f"{a.branch} is not a merge candidate (merge.py candidates)")
    branch, task_id, plan, pr = match[0]
    reg = [r for r in read_jsonl("registry.jsonl") if r["branch"] == branch][-1]
    scope = plans.package_of(plans.find(task_id, plan))  # the package, even if the registry says `docs` (rules.md 19)
    rounds = max((reports.round_of(r) for r in T.review_reports(scope, task_id)), default=0)
    run_id = f"{today()}-merge-{task_id}-r{rounds + 1}"
    base = T.git("rev-parse", "HEAD")
    before = T.git("rev-parse", branch)
    T.git("switch", "-q", branch)
    r = T.sh(["git", "rebase", "-q", base], check=False)
    if r.returncode:
        T.sh(["git", "rebase", "--abort"], check=False)
        T.git("switch", "-q", "dev_agent")
        rec = {"run_id": run_id, "kind": "merge", "task_id": task_id, "plan": plan, "scope": scope, "branch": branch,
               "pr": pr, "session": session, "started": T.now(), "prs_created": 0}
        set_status(rec, "blocked — conflicts with dev_agent, rerun the task")
        T.save(rec)
        fail(f"rebase of {branch} conflicts: task blocked; next: merge.py close {run_id}", 1)
    head = T.git("rev-parse", "HEAD")
    changed = head != before
    if changed:
        T.git("push", "-q", "--force-with-lease", "origin", branch)
    T.git("switch", "-q", "dev_agent")
    report = AGENTS_DIR / "reports" / scope / f"{today()}-pr-review-{task_id}-r{rounds + 1}.md"
    rec = {"run_id": run_id, "kind": "merge", "task_id": task_id, "plan": plan, "scope": scope, "branch": branch,
           "pr": pr, "risk": reg["risk"], "session": session, "started": T.now(), "base": base, "head": head,
           "rebased": changed, "round": rounds + 1, "report": str(report.relative_to(REPO)),
           "previous_report": str(T.review_reports(scope, task_id)[-1].relative_to(REPO)) if rounds else None,
           "checks": {}, "ci": None, "prs_created": 0}
    T.save(rec)
    print(f"run {run_id}: {branch} ({task_id}) " + ("rebased and pushed: run `task.py checks` (static and each backend)"
                                                    if changed else "already on dev_agent, head unchanged"))
    print(f"review report path for pr-reviewer: {rec['report']}" +
          (f" (previous: {rec['previous_report']})" if rounds else ""))
    print(f"next: merge.py ci {run_id}")


def cmd_ci(a):
    rec = T.load(a.run_id)
    head = T.git("rev-parse", rec["branch"])
    args = ["pr", "--pr", str(rec["pr"])] if rec["pr"] else ["run", "--branch", rec["branch"], "--base", rec["base"]]
    r = T.script("ci.py", *args, "--timeout", str(a.timeout), check=False)
    print(r.stdout.strip())
    rec["ci"] = {"head": head, "rc": r.returncode, "out": r.stdout[-4000:]}
    if r.returncode == 3:  # CI could not run at all (e.g. Actions disabled on the fork): say so in the plan
        err = (r.stderr.strip().splitlines() or ["ci.py error"])[-1]
        set_status(rec, f"blocked — CI unavailable: {err[:150]}")
        T.save(rec)
        print(f"CI could not run: {err}\nnext: merge.py close {a.run_id}")
        sys.exit(3)
    T.save(rec)
    if r.returncode == 2:
        print(f"CI still running: call `merge.py ci {a.run_id}` again")
    elif r.returncode == 1:
        T.git("switch", "-q", "dev_agent") if T.git("branch", "--show-current") != "dev_agent" else None
        line = next((l for l in r.stdout.splitlines() if l.startswith("NEW-FAILURE")), "CI red")
        set_status(rec, f"blocked — CI red: {line[:150]}")
        T.save(rec)
        print(f"task blocked; next: merge.py close {a.run_id}")
    sys.exit(0 if r.returncode in (0, 4) else r.returncode)


# ------------------------------------------------------------------ decide / gate
def review_problems(rec):
    problems = []
    since = usage.parse_ts(rec["started"])
    if not ev.launches(rec["session"], since).get("pr-reviewer"):
        problems.append("no pr-reviewer was launched in this session since start (rules.md 16)")
    report = REPO / rec["report"]
    if not report.exists():
        problems.append(f"review report {rec['report']} does not exist")
    else:
        if datetime.fromtimestamp(report.stat().st_mtime, timezone.utc) < since:
            problems.append(f"{rec['report']} is older than this run")
    if T.git("rev-parse", rec["branch"]) != rec["head"]:
        problems.append("the branch head changed after start: start again")
    ci = rec.get("ci")  # optional before the review: the PR's checks (gate) are the CI run
    if ci and ci["head"] == rec["head"] and ci["rc"] not in (0, 4):
        problems.append("branch CI is red for this head")
    if rec["rebased"]:
        for k in ["static", *T.profile()["checks"]["qt_backends"]]:
            c = rec["checks"].get(k)
            if not c or c["head"] != rec["head"]:
                problems.append(f"the rebase changed the head: task.py checks RUN {'--backend ' + k if k != 'static' else ''}")
    return problems


def fields(report):
    path = REPO / report
    f = dict(reports.header(path))
    f["summary_text"] = reports.summary(path)
    return f, path.read_text()


def pr_body(rec, text):
    block = T.task_block(REPO / rec["plan"], rec["task_id"])
    title = re.match(rf"## {re.escape(rec['task_id'])}\s+(.*)", block).group(1)
    findings = reports.notes(REPO / rec["report"])
    ci = (rec.get("ci") or {}).get("out", "")
    known = [l for l in ci.splitlines() if l.startswith("KNOWN-UPSTREAM")]
    return "\n".join([
        f"**{rec['task_id']}**: {title}", "",
        f"Plan: `{rec['plan']}`. Review r{rec['round']} by pr-reviewer: **approve**. {fields(rec['report'])[0]['summary_text']}", "",
        *(["Review notes:", *findings, ""] if findings else []),
        "Local checks: flake8 blocking set, layering test, merge_gate lint and the scope's tests under each Qt binding "
        "(task.py/merge.py records). CI: the checks of this PR." + (f" Known upstream/dev failures: {'; '.join(known)}." if known else ""),
        "", f"Agent-Run: {rec['run_id']}", "", "🤖 Generated with [Claude Code](https://claude.com/claude-code)"])


def cmd_decide(a):
    rec = T.load(a.run_id)
    problems = review_problems(rec)
    if problems:
        print("decide refused:\n  " + "\n  ".join(problems))
        sys.exit(1)
    f, text = fields(rec["report"])
    verdict = f.get("verdict")
    rec["verdict"] = verdict
    for key, title in reports.outside(REPO / rec["report"]):  # rules.md 18: problems outside the change
        print(T.script("findings.py", "add", "--scope", rec["scope"], "--kind", "review", "--key", key,
                       "--title", title, "--evidence", rec["report"], "--source", rec["run_id"]).stdout.strip())
    if verdict == "changes":
        set_status(rec, f"blocked — review: {f['summary_text'][:160] or 'changes requested'}")
    elif verdict == "reject":
        if rec["pr"]:
            T.sh(["gh", "pr", "close", str(rec["pr"]), "-R", fork(), "-c", f"Rejected by review: {f['summary_text'][:300]}"])
        T.script("registry.py", "set-status", "--branch", rec["branch"], "--status", "closed")
        set_status(rec, f"blocked — rejected by review: {f['summary_text'][:150]}")
    elif verdict == "approve":
        body = pr_body(rec, text)
        if rec["pr"]:
            T.sh(["gh", "pr", "ready", str(rec["pr"]), "-R", fork()])
            T.sh(["gh", "pr", "comment", str(rec["pr"]), "-R", fork(), "--body", body])
        else:
            if T.script("budget.py", "check", "--kind", "pr", check=False).returncode:
                set_status(rec, f"done — branch {rec['branch']}, review approve, PR cap reached")
                T.save(rec)
                print(f"PR cap reached: branch left pushed; next: merge.py close {a.run_id}")
                return
            block = T.task_block(REPO / rec["plan"], rec["task_id"])
            title = re.match(rf"## {re.escape(rec['task_id'])}\s+(.*)", block).group(1)
            r = T.sh(["gh", "pr", "create", "-R", fork(), "--base", "dev_agent", "--head", rec["branch"],
                      "--label", "agent-made", "--title", f"{rec['task_id']}: {title}"[:120], "--body", body])
            rec["pr"] = int(re.search(r"/pull/(\d+)", r.stdout).group(1))
            rec["prs_created"] = 1
        T.script("registry.py", "set-status", "--branch", rec["branch"], "--status", "open", "--pr", str(rec["pr"]))
        print(f"PR #{rec['pr']} ready; next: merge.py gate {a.run_id}")
    else:
        fail(f"{rec['report']} has no valid verdict line (approve|changes|reject)")
    T.save(rec)
    if verdict != "approve":
        print(f"verdict {verdict}: task {rec.get('outcome_status')}; next: merge.py close {a.run_id}")


def cmd_gate(a):
    rec = T.load(a.run_id)
    if rec.get("verdict") != "approve" or not rec.get("pr"):
        fail("gate needs an approved review and an open PR (merge.py decide)")
    r = T.script("ci.py", "pr", "--pr", str(rec["pr"]), "--timeout", str(a.timeout), check=False)
    print(r.stdout.strip())
    if r.returncode == 3:
        err = (r.stderr.strip().splitlines() or ["ci.py error"])[-1]
        set_status(rec, f"blocked — PR CI unavailable: {err[:150]}")
        T.save(rec)
        print(f"PR checks could not be read: {err}\nnext: merge.py close {a.run_id}")
        sys.exit(3)
    if r.returncode == 2:
        print(f"PR checks still running: call `merge.py gate {a.run_id}` again")
        sys.exit(2)
    if r.returncode == 1:
        line = next((l for l in r.stdout.splitlines() if l.startswith("NEW-FAILURE")), "PR CI red")
        set_status(rec, f"blocked — PR CI red: {line[:150]}")
        T.save(rec)
        print(f"next: merge.py close {a.run_id}")
        sys.exit(1)
    for line in re.findall(r"^\s*record: (python3 .*)$", r.stdout + (rec.get("ci") or {}).get("out", ""), re.M):
        print(T.script("findings.py", *__import__("shlex").split(line)[2:]).stdout.strip())
    g = T.script("merge_gate.py", "check", "--branch", rec["branch"], "--plan", rec["plan"], "--task-id",
                 rec["task_id"], "--review", rec["report"], check=False)
    line = (g.stdout.strip() or g.stderr.strip())
    print(line)
    if g.returncode == 0:
        # the PR's checks validated this head: no second CI run on the merge commit
        T.sh(["gh", "pr", "merge", str(rec["pr"]), "-R", fork(), "--merge",
              "--subject", f"Merge PR #{rec['pr']}: {rec['task_id']} [skip ci]"])
        T.git("pull", "-q", "--ff-only", "origin", "dev_agent")
        T.script("registry.py", "set-status", "--branch", rec["branch"], "--status", "merged")
        set_status(rec, f"done — PR #{rec['pr']} merged (auto: {line.removeprefix('AUTO-MERGE: ')[:140]})")
        key = re.search(r"^- finding:\s*(.+)$", T.task_block(REPO / rec["plan"], rec["task_id"]), re.M)
        if key:
            T.script("findings.py", "set-status", "--key", key.group(1).strip(), "--status", "closed", "--task-id", rec["task_id"])
    elif g.returncode == 1:
        set_status(rec, f"done — PR #{rec['pr']} open, awaiting the human: {line.removeprefix('HUMAN: ')[:160]}")
    else:
        set_status(rec, f"blocked — merge gate: {line[:160]}")
    T.save(rec)
    print(f"next: merge.py close {a.run_id}")


def cmd_close(a):
    rec = T.load(a.run_id)
    if T.git("branch", "--show-current") != "dev_agent":
        fail("be on dev_agent")
    if not rec.get("outcome_status"):
        fail("nothing decided yet: ci / decide / gate first")
    other = [f"{x} {p}" for x, p in gitx.porcelain() if not p.startswith(".agents/")]
    if other:
        fail("product files changed on dev_agent: " + ", ".join(other))
    T.script("ledger.py", "add", "--run-id", rec["run_id"], "--command", "optimize-merge", "--scope", rec["scope"],
             "--session", rec["session"], "--since", rec["started"], "--outcome", "ok",
             "--prs-opened", str(rec["prs_created"]), "--note", f"{rec['task_id']}: {rec['outcome_status']}"[:300])
    T.script("status.py", "--write")
    T.git("add", ".agents")
    T.git("commit", "-q", "-m", f"Log /optimize-merge {rec['task_id']} ({rec['outcome_status'][:80]}) [skip ci]\n\nAgent-Run: {rec['run_id']}")
    T.git("push", "-q", "origin", "dev_agent")
    rec["closed"] = T.now()
    T.save(rec)
    print(f"closed {rec['run_id']}: {rec['outcome_status']}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sync").set_defaults(fn=cmd_sync)
    c = sub.add_parser("candidates")
    c.add_argument("filter", nargs="?")
    c.set_defaults(fn=cmd_candidates)
    s = sub.add_parser("start")
    s.add_argument("--branch", required=True)
    s.set_defaults(fn=cmd_start)
    for name, fn in (("ci", cmd_ci), ("decide", cmd_decide), ("gate", cmd_gate), ("close", cmd_close)):
        x = sub.add_parser(name)
        x.add_argument("run_id")
        if name in ("ci", "gate"):
            x.add_argument("--timeout", type=int, default=540, help="seconds to wait for checks (exit 2 = again)")
        x.set_defaults(fn=fn)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

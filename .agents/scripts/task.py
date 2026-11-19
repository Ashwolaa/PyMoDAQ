#!/usr/bin/env python3
"""One /optimize-run task, step by step. Each step is done or verified by this script, so a step cannot be skipped
or claimed without evidence (rules.md 16). Usage, in this order:

  task.py start --task-id T --plan P        on dev_agent: checks status and budget, computes the run id
                                             (rework: -r<N>), creates the branch or rebases the existing one
  (launch the specialist; it commits product files on the branch)
  task.py checks RUN [--backend B]          on the branch, committed head: without --backend the static checks
                                             (lint_blocking, layering, merge_gate lint); with it the touched
                                             scopes' tests under that Qt binding. Tests failing here are rerun on
                                             the base commit: failing there too = pre-existing
  git push [--force-with-lease] origin <branch>
  task.py ci RUN                            ci.py run on the pushed head (--timeout 540); exit 2 = call again
  task.py finish RUN [--note TXT]           verifies everything for the current head (see below), switches to
                                             dev_agent, writes registry, plan status, findings and ledger
  (overwrite .agents/handoff/<scope>.md)
  task.py close RUN                         requires the handoff rewritten during the run; commits and pushes dev_agent
  task.py block RUN --reason TXT            give up on the task: plan `blocked — <reason>`, ledger, back to dev_agent
  task.py show RUN                          the run record

finish refuses unless: a specialist (spec-* or test-agent) was launched in this session since start; the main session
made no Edit/Write to a product file; static checks and every [checks].qt_backends test run are recorded for the
current head with no new failure; merge_gate lint passes; origin has the head; CI is recorded for the head with exit
0 or 4 (known upstream failures, filed with findings.py by finish).
Run records live in <git common dir>/agent-runs/, outside the worktree, so they never reach a branch or a PR.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, load_toml, read_jsonl, today

REPO = AGENTS_DIR.parent
SCRIPTS = AGENTS_DIR / "scripts"
PY = sys.executable


def sh(cmd, check=True, cwd=REPO, shell=False):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, shell=shell,
                       executable="/bin/bash" if shell else None)
    if check and r.returncode:
        fail(f"{cmd if shell else ' '.join(cmd)}: {(r.stderr or r.stdout).strip()[-800:]}")
    return r


def git(*args, check=True):
    return sh(["git", *args], check=check).stdout.strip()


def script(name, *args, check=True):
    r = sh([PY, str(SCRIPTS / name), *args], check=False)
    if check and r.returncode:
        fail(f"{name} {' '.join(args)}: {(r.stdout + r.stderr).strip()}")
    return r


def runs_dir() -> Path:
    d = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir")) / "agent-runs"
    d.mkdir(exist_ok=True)
    return d


def load(run_id) -> dict:
    p = runs_dir() / f"{run_id}.json"
    if not p.exists():
        fail(f"no run record {run_id} (task.py start first)")
    return json.loads(p.read_text())


def save(rec):
    (runs_dir() / f"{rec['run_id']}.json").write_text(json.dumps(rec, indent=1, sort_keys=True))


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_on(branch):
    cur = git("branch", "--show-current")
    if cur != branch:
        fail(f"be on {branch} (you are on {cur or 'a detached head'})")
    dirty = git("status", "--porcelain")
    if dirty:
        fail(f"commit or drop the changes first:\n{dirty}")


def task_block(plan: Path, task_id: str) -> str:
    m = re.search(rf"^## {re.escape(task_id)}\b.*?(?=^## |\Z)", plan.read_text(), re.M | re.S)
    if not m:
        fail(f"{task_id} not found in {plan}")
    return m.group(0)


def field(block, name):
    m = re.search(rf"\b{name}:\s*([\w.-]+)", block)
    return m.group(1) if m else None


def review_reports(scope, task_id):
    return sorted((AGENTS_DIR / "reports" / scope).glob(f"*-pr-review-{task_id}*.md"))


def changes_rounds(scope, task_id):
    return sum(1 for p in review_reports(scope, task_id) if re.search(r"^verdict:\s*changes", p.read_text(), re.M))


def profile():
    return load_toml("profile.toml")


def env_prefix(backend=None):
    pr = profile()
    parts = [pr["tools"].get("env", "")]
    if backend:
        ck = pr["checks"]
        parts.append(f"export {ck['qt_backend_env'].format(backend=backend)} QT_API={backend} {ck.get('qt_headless', '')}")
    return "; ".join(p for p in parts if p)


def touched_scopes(base, head):
    pr = profile()
    root, order = pr["scopes"].get("root", "packages"), pr["scopes"]["order"]
    changed = git("diff", "--name-only", f"{base}...{head}").splitlines()
    return [s for s in order if any(c.startswith(f"{root}/{s}/") for c in changed)]


# ------------------------------------------------------------------ start
def cmd_start(a):
    clean_on(profile()["project"].get("integration_branch", "dev_agent"))
    script("budget.py", "check")
    plan = Path(a.plan) if Path(a.plan).is_absolute() else REPO / a.plan
    block = task_block(plan, a.task_id)
    status = re.search(r"^- status:\s*(.*)$", block, re.M).group(1)
    scope, specialty, risk = field(block, "scope"), field(block, "specialty"), field(block, "risk") or "medium"
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not session:
        fail("CLAUDE_CODE_SESSION_ID is not set: run task.py from the coordinator's session")
    base = git("rev-parse", "HEAD")
    rows = [r for r in read_jsonl("registry.jsonl") if r.get("task_id") == a.task_id]
    if status.startswith("blocked — review"):
        n = changes_rounds(scope, a.task_id)
        if n >= 2:
            script("plan.py", "set-status", str(plan), a.task_id, "blocked — review: still failing after 2 rounds, for the human")
            fail("two review rounds said changes: the task goes to the human (plan updated; commit it with the handoff)", 1)
        if not rows:
            fail(f"{a.task_id} has no registered branch to rework")
        branch, run_id, rework = rows[-1]["branch"], f"{today()}-run-{a.task_id}-r{n}", n
        git("switch", "-q", branch)
        r = sh(["git", "rebase", "-q", base], check=False)
        if r.returncode:
            sh(["git", "rebase", "--abort"], check=False)
            git("switch", "-q", "dev_agent")
            script("plan.py", "set-status", str(plan), a.task_id, "blocked — conflicts with dev_agent, rerun the task")
            fail(f"rebase of {branch} on dev_agent conflicts: task blocked", 1)
    elif status.startswith("approved"):
        if rows:
            fail(f"{a.task_id} already has a branch ({rows[-1]['branch']}); a rework needs status 'blocked — review'")
        branch = f"agent/{scope}/{specialty}/{today()}"
        exists = lambda b: git("rev-parse", "-q", "--verify", b, check=False) or git("ls-remote", "origin", f"refs/heads/{b}")
        if exists(branch):
            title = re.match(rf"## {re.escape(a.task_id)}\s+(.*)", block).group(1)
            branch += "-" + "-".join(re.findall(r"[a-z0-9]+", title.lower())[:3])
        if exists(branch):
            fail(f"{branch} exists too: pick another name by hand")
        run_id, rework = f"{today()}-run-{a.task_id}", 0
        git("switch", "-q", "-c", branch, base)
    else:
        fail(f"{a.task_id} is '{status}': only approved tasks, or tasks blocked by review (rework), can run")
    rec = {"run_id": run_id, "task_id": a.task_id, "plan": str(plan.relative_to(REPO)) if plan.is_relative_to(REPO) else str(plan), "scope": scope,
           "specialty": specialty, "risk": risk, "branch": branch, "rework": rework, "session": session,
           "started": now(), "base": base, "checks": {}, "ci": None}
    save(rec)
    print(f"run {run_id}: on {branch}" + (f" (rework of review r{rework}, rebased on dev_agent)" if rework else ""))
    print(f"next: launch the {specialty} specialist with the task block"
          + (f" and the latest review report ({review_reports(scope, a.task_id)[-1].relative_to(REPO)})" if rework else "")
          + f", then `task.py checks {run_id}`")


# ------------------------------------------------------------------ checks
def pytest_failures(out):
    return sorted({m.split(" - ")[0] for m in re.findall(r"^(?:FAILED|ERROR) (\S+(?: - .*)?)$", out, re.M)})


def cmd_checks(a):
    rec = load(a.run_id)
    clean_on(rec["branch"])
    head = git("rev-parse", "HEAD")
    ck = profile()["checks"]
    scopes = touched_scopes(rec["base"], head)
    if a.backend:
        if a.backend not in ck["qt_backends"]:
            fail(f"--backend must be one of {ck['qt_backends']}")
        result = {"head": head, "scopes": {}}
        for s in scopes:
            cmd = f"{env_prefix(a.backend)}; {ck['test'].format(scope=s)} -q -rfE -p no:cacheprovider"
            r = sh(cmd, check=False, shell=True)
            tail = (r.stdout.strip().splitlines() or ["(no output)"])[-1]
            failed = pytest_failures(r.stdout)
            entry = {"rc": r.returncode, "summary": tail, "failed": failed, "preexisting": []}
            if r.returncode and not failed:
                entry["error"] = "pytest failed without a failing test id (crash or collection error): " + \
                                 (r.stdout + r.stderr).strip()[-400:]
            if failed:  # rerun only those on the base commit: failing there too = pre-existing
                git("switch", "-q", "--detach", rec["base"])
                try:
                    ids = " ".join(shlex.quote(f) for f in failed)
                    b = sh(f"{env_prefix(a.backend)}; {ck['test'].format(scope=s)} -q -rfE -p no:cacheprovider {ids}",
                           check=False, shell=True)
                    entry["preexisting"] = [f for f in failed if f in pytest_failures(b.stdout)]
                finally:
                    git("switch", "-q", rec["branch"])
            entry["new"] = [f for f in failed if f not in entry["preexisting"]]
            result["scopes"][s] = entry
            print(f"{a.backend} {s}: {tail}" + (f"; pre-existing: {', '.join(entry['preexisting'])}" if entry["preexisting"] else "")
                  + (f"; NEW FAILURES: {', '.join(entry['new'])}" if entry["new"] else "") + (f"; {entry['error']}" if entry.get("error") else ""))
        if not scopes:
            print(f"{a.backend}: no package touched, no scope tests to run")
        rec["checks"][a.backend] = result
    else:
        result = {"head": head, "items": {}}
        for s in scopes:
            r = sh(f"{env_prefix()}; {ck['lint_blocking'].format(scope=s)}", check=False, shell=True)
            result["items"][f"lint_blocking {s}"] = {"rc": r.returncode, "out": (r.stdout + r.stderr).strip()[-300:]}
        r = sh(f"{env_prefix('pyqt6')}; {ck['layering']} -q -p no:cacheprovider", check=False, shell=True)
        result["items"]["layering"] = {"rc": r.returncode, "out": (r.stdout.strip().splitlines() or [""])[-1]}
        r = script("merge_gate.py", "lint", "--branch", rec["branch"], "--task-id", rec["task_id"], "--base", rec["base"],
                   check=False)
        result["items"]["merge_gate lint"] = {"rc": r.returncode, "out": (r.stdout + r.stderr).strip()}
        for k, v in result["items"].items():
            print(f"{'ok  ' if v['rc'] == 0 else 'FAIL'} {k}: {v['out'].splitlines()[-1] if v['out'] else ''}")
        rec["checks"]["static"] = result
    save(rec)


# ------------------------------------------------------------------ ci
def cmd_ci(a):
    rec = load(a.run_id)
    head = git("rev-parse", rec["branch"])
    r = script("ci.py", "run", "--branch", rec["branch"], "--base", rec["base"], "--timeout", "540", check=False)
    print(r.stdout.strip() + ("\n" + r.stderr.strip() if r.stderr.strip() else ""))
    if r.returncode == 2:
        print(f"CI still running: call `task.py ci {a.run_id}` again")
    rec["ci"] = {"head": head, "rc": r.returncode, "out": r.stdout[-4000:]}
    save(rec)
    sys.exit(0 if r.returncode in (0, 4) else r.returncode)


# ------------------------------------------------------------------ finish / close / block
def evidence(rec):
    """Problems that forbid `finish`, read from the transcripts and the run record."""
    import usage
    problems = []
    since = usage.parse_ts(rec["started"])
    rows = list(usage.requests(rec["session"], since))
    launched = {r["agent"] for r in rows if r["agent"] != "main"}
    if not any(a.startswith("spec-") or a == "test-agent" for a in launched):
        problems.append("no specialist was launched in this run (rules.md 16)")
    for path, sid, agent in usage.transcripts(rec["session"]):
        if agent != "main":
            continue
        for line in open(path, encoding="utf-8", errors="replace"):
            if '"tool_use"' not in line or '"file_path"' not in line:
                continue
            d = json.loads(line)
            if usage.parse_ts(d.get("timestamp", "1970-01-01T00:00:00Z")) < since:
                continue
            for c in (d.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use" and c.get("name") in ("Edit", "Write", "NotebookEdit"):
                    fp = (c.get("input") or {}).get("file_path", "")
                    if fp.startswith(str(REPO)) and "/.agents/" not in fp:
                        problems.append(f"the coordinator edited a product file itself: {fp} (rules.md 16)")
    head = git("rev-parse", rec["branch"])
    static = rec["checks"].get("static")
    if not static or static["head"] != head:
        problems.append("static checks not recorded for the current head: task.py checks RUN")
    elif any(v["rc"] for v in static["items"].values()):
        problems.append("static checks failed: " + ", ".join(k for k, v in static["items"].items() if v["rc"]))
    for b in profile()["checks"]["qt_backends"]:
        t = rec["checks"].get(b)
        if not t or t["head"] != head:
            problems.append(f"tests under {b} not recorded for the current head: task.py checks RUN --backend {b}")
            continue
        for s, e in t["scopes"].items():
            if e.get("new") or e.get("error"):
                problems.append(f"{b} {s}: new failures {e.get('new') or e.get('error')}")
    remote = git("ls-remote", "origin", f"refs/heads/{rec['branch']}").split()
    if not remote or remote[0] != head:
        problems.append(f"origin does not have {head[:9]}: push the branch")
    ci = rec.get("ci")
    if not ci or ci["head"] != head:
        problems.append("CI not recorded for the current head: task.py ci RUN")
    elif ci["rc"] not in (0, 4):
        problems.append(f"CI is not green (ci.py exit {ci['rc']})")
    return problems


def ci_word(rec):
    return {0: "green", 4: "green except known upstream failures"}.get((rec.get("ci") or {}).get("rc"), "?")


def cmd_finish(a):
    rec = load(a.run_id)
    problems = evidence(rec)
    if problems:
        print("finish refused:\n  " + "\n  ".join(problems))
        sys.exit(1)
    clean_on(rec["branch"])
    git("switch", "-q", "dev_agent")
    if not rec["rework"]:
        script("registry.py", "add", "--run-id", rec["run_id"], "--scope", rec["scope"], "--specialty", rec["specialty"],
               "--branch", rec["branch"], "--risk", rec["risk"], "--task-id", rec["task_id"], "--status", "pushed")
    status = f"done — branch {rec['branch']}, CI {ci_word(rec)}" + \
             (f", reworked after review r{rec['rework']}" if rec["rework"] else "") + ", awaiting review"
    script("plan.py", "set-status", rec["plan"], rec["task_id"], status)
    for line in re.findall(r"^\s*record: (python3 .*)$", rec["ci"]["out"], re.M):
        args = shlex.split(line)[2:]  # drop "python3 .agents/scripts/findings.py"
        print(script("findings.py", *args).stdout.strip())
    pre = sorted({f for b in profile()["checks"]["qt_backends"] for e in rec["checks"][b]["scopes"].values()
                  for f in e["preexisting"]})
    note = "; ".join(x for x in [a.note, f"pre-existing local failures: {', '.join(pre)}" if pre else ""] if x)
    script("ledger.py", "add", "--run-id", rec["run_id"], "--command", "optimize-run", "--scope", rec["scope"],
           "--session", rec["session"], "--since", rec["started"], "--outcome", "ok", "--note", note or status)
    rec["finished"] = now()
    save(rec)
    print(f"finished {rec['run_id']}: {status}")
    print(f"next: overwrite .agents/handoff/{rec['scope']}.md, then `task.py close {rec['run_id']}`")


def cmd_close(a):
    rec = load(a.run_id)
    if not rec.get("finished") and not rec.get("blocked"):
        fail("finish (or block) the run first")
    if git("branch", "--show-current") != "dev_agent":
        fail("be on dev_agent")
    handoff = AGENTS_DIR / "handoff" / f"{rec['scope']}.md"
    changed = git("status", "--porcelain", "--", str(handoff.relative_to(REPO)))
    if not changed:
        fail(f"rewrite {handoff.relative_to(REPO)} for this run first (formats.md: handoff)")
    lines = len(handoff.read_text().splitlines())
    limit = profile()["limits"].get("handoff_max_lines", 40)
    if lines > limit:
        fail(f"{handoff.name} has {lines} lines > {limit}")
    porcelain = sh(["git", "status", "--porcelain"]).stdout  # unstripped: the first line starts with a space
    other = [l for l in porcelain.splitlines() if l and not l[3:].startswith(".agents/")]
    if other:
        fail("product files changed on dev_agent: " + ", ".join(other))
    git("add", ".agents")
    what = "blocked" if rec.get("blocked") else f"branch pushed, CI {ci_word(rec)}"
    git("commit", "-q", "-m", f"Log /optimize-run {rec['task_id']} ({what})\n\nAgent-Run: {rec['run_id']}")
    git("push", "-q", "origin", "dev_agent")
    rec["closed"] = now()
    save(rec)
    print(f"closed {rec['run_id']}: state committed and pushed on dev_agent")


def cmd_block(a):
    rec = load(a.run_id)
    if git("status", "--porcelain"):
        fail("commit or drop the changes on the branch first")
    if git("branch", "--show-current") != "dev_agent":
        git("switch", "-q", "dev_agent")
    script("plan.py", "set-status", rec["plan"], rec["task_id"], f"blocked — {a.reason}")
    script("ledger.py", "add", "--run-id", rec["run_id"], "--command", "optimize-run", "--scope", rec["scope"],
           "--session", rec["session"], "--since", rec["started"], "--outcome", "failed", "--note", a.reason)
    rec["blocked"] = a.reason
    save(rec)
    print(f"blocked {rec['run_id']}: {a.reason}\nnext: overwrite .agents/handoff/{rec['scope']}.md, then `task.py close {rec['run_id']}`")


def cmd_show(a):
    print(json.dumps(load(a.run_id), indent=1, sort_keys=True))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--task-id", required=True)
    s.add_argument("--plan", required=True)
    s.set_defaults(fn=cmd_start)
    c = sub.add_parser("checks")
    c.add_argument("run_id")
    c.add_argument("--backend", default=None)
    c.set_defaults(fn=cmd_checks)
    for name, fn in (("ci", cmd_ci), ("close", cmd_close), ("show", cmd_show)):
        x = sub.add_parser(name)
        x.add_argument("run_id")
        x.set_defaults(fn=fn)
    f = sub.add_parser("finish")
    f.add_argument("run_id")
    f.add_argument("--note", default="")
    f.set_defaults(fn=cmd_finish)
    b = sub.add_parser("block")
    b.add_argument("run_id")
    b.add_argument("--reason", required=True)
    b.set_defaults(fn=cmd_block)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

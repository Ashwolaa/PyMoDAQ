#!/usr/bin/env python3
"""CI for agent branches and PRs, with failures compared against upstream/dev. Usage:

  ci.py workflows --branch B [--base dev_agent]   list the workflows that apply to the branch's changes
  ci.py run --branch B [--base dev_agent] [--timeout 1500] [--no-rerun]
      dispatch those workflows on the pushed branch head (workflow_dispatch) and wait for them
  ci.py pr --pr N [--timeout 1500] [--no-rerun]
      wait for the checks of PR N on the fork

Failed jobs are rerun once (--no-rerun to skip). A job still failing is compared with the same job on upstream/dev
(the last runs of the same workflow on branch `dev` of `[project].upstream`): a hard crash (Fatal Python error:
segfault/abort/bus error) matches a crash there, failed tests match when every failing test id also failed there.
  exit 0 = green, 1 = red (a failure upstream/dev does not have), 2 = pending at timeout, 3 = error,
  4 = green except failures that upstream/dev has too (printed as `KNOWN-UPSTREAM <scope> | <job> | <signature> | <url>`)

Why dispatch: the fork's workflows trigger on `push: branches: '*'`, and `*` does not match the `/` in agent/... names.
Why jobs: tests-pymodaq.yml sets continue-on-error on its test jobs, so the run conclusion says success anyway.
"""
import argparse
import fnmatch
import json
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, load_toml

REPO_ROOT = AGENTS_DIR.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
BAD = ("failure", "cancelled", "timed_out", "startup_failure")
UPSTREAM_RUNS = 15
_listed: list = []


def sh(*cmd: str, check: bool = True) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if r.returncode and check:
        fail(f"{' '.join(cmd)}: {r.stderr.strip() or r.stdout.strip()}", code=3)
    return r.stdout


def project() -> dict:
    return load_toml("profile.toml")["project"]


def workflows_listed() -> list:
    if not _listed:
        _listed.extend(json.loads(sh("gh", "workflow", "list", "-R", project()["fork"], "--all",
                                     "--json", "path,state,name")))
    return _listed


def file_of(display: str) -> str | None:
    return next((Path(w["path"]).name for w in workflows_listed() if w["name"] == display), None)


def triggers(text: str) -> dict:
    """Top-level `on:` keys of a workflow, with the pull_request paths filter (stdlib only: no YAML parser)."""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"^(on|'on'|\"on\"):\s*$", l))
    except StopIteration:
        return {}
    block = []
    for l in lines[start + 1:]:
        if l.strip() and not l.startswith((" ", "\t")):
            break
        block.append(l)
    keys, current, paths, in_paths, key_indent = {}, None, None, False, None
    for l in block:
        if not l.strip() or l.strip().startswith("#"):
            continue
        indent = len(l) - len(l.lstrip())
        m = re.match(r"^\s*([\w-]+):", l)
        if key_indent is None and m:
            key_indent = indent
        if m and indent == key_indent:
            current = m.group(1)
            keys[current] = None
            in_paths = False
            continue
        if current == "pull_request":
            if m and m.group(1) == "paths":
                in_paths, paths = True, []
                continue
            if m:
                in_paths = False
            item = re.match(r"^\s*-\s*['\"]?([^'\"#]+?)['\"]?\s*(#.*)?$", l)
            if in_paths and item:
                paths.append(item.group(1).strip())
    if "pull_request" in keys:
        keys["pull_request"] = paths  # None = no paths filter
    return keys


def scope_of(wf_file: str) -> str:
    """Package a workflow tests, from its first `packages/<scope>/**` path filter; `repo` otherwise."""
    on = triggers((WORKFLOWS / wf_file).read_text()) if (WORKFLOWS / wf_file).exists() else {}
    for p in on.get("pull_request") or []:
        m = re.match(r"packages/(\w+)/", p)
        if m:
            return m.group(1)
    return "repo"


def applicable(branch: str, base: str) -> list:
    changed = [p for p in sh("git", "diff", "--name-only", f"{base}...{branch}").splitlines() if p]
    if not changed:
        fail(f"{branch} has no changes against {base}", code=3)
    active = {w["path"]: w["state"] for w in workflows_listed()}
    out = []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        on = triggers(wf.read_text())
        if "workflow_dispatch" not in on or "pull_request" not in on \
                or active.get(f".github/workflows/{wf.name}") != "active":
            continue
        paths = on["pull_request"]
        if paths is None or any(fnmatch.fnmatch(c, p) for c in changed for p in paths):
            out.append(wf.name)
    return out


# ---------------------------------------------------------------- failure signatures
def signature(repo: str, run_id: int, job_id: int) -> dict:
    log = sh("gh", "run", "view", str(run_id), "-R", repo, "--job", str(job_id), "--log-failed", check=False)
    crash = re.search(r"Fatal Python error: (\w+)", log)
    tests = sorted({t.split(" - ")[0] for t in re.findall(r"FAILED (tests/\S+(?: - [^\n]*)?)", log)})
    if crash:
        return {"kind": "crash", "detail": crash.group(1), "tests": tests}
    if tests:
        return {"kind": "tests", "detail": f"{len(tests)} failed", "tests": tests}
    if "exceeded the maximum execution time" in log:
        return {"kind": "timeout", "detail": "job timeout", "tests": []}
    code = re.search(r"exit code (\d+)", log)
    return {"kind": "other", "detail": f"exit {code.group(1) if code else '?'}", "tests": []}


def describe(sig: dict) -> str:
    if sig["kind"] == "crash":
        return f"crash (Fatal Python error: {sig['detail']})"
    if sig["kind"] == "tests":
        return "failed " + ", ".join(sig["tests"][:3]) + (" ..." if len(sig["tests"]) > 3 else "")
    return sig["detail"]


def loose(job_name: str) -> str:
    """`tests (ubuntu-latest, 3.12, pyside6)` -> `tests (ubuntu-latest, pyside6)`: python version dropped."""
    return re.sub(r",\s*3\.\d+", "", job_name)


def upstream_match(wf_file: str, job_name: str, sig: dict):
    """URL of an upstream/dev run where the same job failed the same way, else None."""
    if sig["kind"] not in ("crash", "tests"):
        return None
    up, base = project()["upstream"], project().get("base_branch", "dev")
    runs = json.loads(sh("gh", "run", "list", "-R", up, "--workflow", wf_file, "--branch", base,
                         "--limit", str(UPSTREAM_RUNS), "--json", "databaseId,url", check=False) or "[]")
    jobs_of = {}
    for exact in (True, False):
        for r in runs:
            if r["databaseId"] not in jobs_of:
                jobs_of[r["databaseId"]] = json.loads(sh("gh", "run", "view", str(r["databaseId"]), "-R", up,
                                                         "--json", "jobs", check=False) or '{"jobs": []}')["jobs"]
            for j in jobs_of[r["databaseId"]]:
                same = j["name"] == job_name if exact else loose(j["name"]) == loose(job_name)
                if not same or j["conclusion"] != "failure":
                    continue
                theirs = signature(up, r["databaseId"], j["databaseId"])
                if sig["kind"] == "crash" and theirs["kind"] == "crash":
                    return r["url"]
                if sig["kind"] == "tests" and set(sig["tests"]) <= set(theirs["tests"]):
                    return r["url"]
    return None


# ---------------------------------------------------------------- waiting and verdict
def failed_jobs(run_ids: dict) -> list:
    """[(workflow file, job name, run id, job id)] of failed jobs. Jobs, not run conclusions: see module doc."""
    out = []
    for wf, rid in run_ids.items():
        for j in json.loads(sh("gh", "run", "view", str(rid), "-R", project()["fork"], "--json", "jobs"))["jobs"]:
            if j["conclusion"] in BAD:
                out.append((wf, j["name"], rid, j["databaseId"]))
    return out


def wait_runs(run_ids, deadline: float):
    while True:
        st = [json.loads(sh("gh", "run", "view", str(r), "-R", project()["fork"], "--json", "status"))["status"]
              for r in run_ids]
        if all(s == "completed" for s in st):
            return
        if time.time() > deadline:
            print(f"CI pending at timeout (runs {', '.join(map(str, run_ids))})")
            sys.exit(2)
        time.sleep(30)


def verdict(run_ids: dict, deadline: float, rerun: bool):
    fork = project()["fork"]
    bad = failed_jobs(run_ids)
    if bad and rerun:
        print("failed jobs, rerunning them once: " + "; ".join(f"{wf}: {job}" for wf, job, _, _ in bad))
        rerun_ids = sorted({rid for _, _, rid, _ in bad})
        for rid in rerun_ids:
            sh("gh", "run", "rerun", str(rid), "--failed", "-R", fork)
        time.sleep(20)
        wait_runs(rerun_ids, deadline)
        first = {(wf, job) for wf, job, _, _ in bad}
        bad = failed_jobs({wf: rid for wf, rid in run_ids.items() if rid in rerun_ids})
        flaky = first - {(wf, job) for wf, job, _, _ in bad}
        if flaky:
            print("flaky (failed, then passed on rerun): " + "; ".join(f"{wf}: {job}" for wf, job in sorted(flaky)))
    for wf, rid in sorted(run_ids.items()):
        n = sum(1 for b in bad if b[0] == wf)
        print(f"  {'FAILED' if n else 'ok':7} {wf}  https://github.com/{fork}/actions/runs/{rid}")
    if not bad:
        print("CI green")
        return
    new, known = [], []
    for wf, job, rid, jid in bad:
        sig = signature(fork, rid, jid)
        url = upstream_match(wf, job, sig)
        (known if url else new).append((wf, job, rid, sig, url))
    for wf, job, rid, sig, url in known:
        scope = scope_of(wf)
        print(f"KNOWN-UPSTREAM {scope} | {job} | {describe(sig)} | {url}")
        key = f"{wf}|{loose(job)}|{sig['kind']}" + (f"|{','.join(sig['tests'])}" if sig["kind"] == "tests" else "")
        title = f"CI {wf} {loose(job)}: {describe(sig)}, also on upstream/dev"
        print(f"  record: python3 .agents/scripts/findings.py add --scope {scope} --kind ci-upstream "
              f"--key {shlex.quote(key)} --title {shlex.quote(title)} "
              f"--evidence https://github.com/{fork}/actions/runs/{rid} --evidence {url}")
    if new:
        for wf, job, rid, sig, _ in new:
            print(f"NEW-FAILURE {scope_of(wf)} | {job} | {describe(sig)} | gh run view {rid} --log-failed -R {fork}")
        print("CI red")
        sys.exit(1)
    print("CI green except failures upstream/dev has too (run each `record:` line on dev_agent)")
    sys.exit(4)


def cmd_workflows(a):
    for name in applicable(a.branch, a.base):
        print(name)


def cmd_run(a):
    fork = project()["fork"]
    head = sh("git", "rev-parse", a.branch).strip()
    remote = sh("git", "ls-remote", "origin", f"refs/heads/{a.branch}").split()
    if not remote or remote[0] != head:
        fail(f"push {a.branch} first: origin has {remote[0][:9] if remote else 'nothing'}, local is {head[:9]}", code=3)
    names = applicable(a.branch, a.base)
    if not names:
        print("no workflow applies to these changes: nothing to run")
        return
    since = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=60)  # clock skew
    for name in names:
        sh("gh", "workflow", "run", name, "-R", fork, "--ref", a.branch)
    print(f"dispatched on {a.branch} @ {head[:9]}: {', '.join(names)}")
    deadline = time.time() + a.timeout
    while True:
        time.sleep(30)
        runs = json.loads(sh("gh", "run", "list", "-R", fork, "--branch", a.branch, "--event", "workflow_dispatch",
                             "--limit", "50", "--json", "databaseId,workflowName,status,headSha,createdAt"))
        latest = {}
        for r in runs:  # gh lists newest first
            wf = file_of(r["workflowName"])
            created = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            if r["headSha"] == head and created >= since and wf in names and wf not in latest:
                latest[wf] = r
        if len(latest) == len(names) and all(r["status"] == "completed" for r in latest.values()):
            break
        if time.time() > deadline:
            print(f"CI pending after {a.timeout}s: {', '.join(sorted(set(names) - set(latest)))}")
            sys.exit(2)
    verdict({wf: r["databaseId"] for wf, r in latest.items()}, deadline, a.rerun_failed)


def cmd_pr(a):
    fork = project()["fork"]
    deadline = time.time() + a.timeout
    subprocess.run(["timeout", str(a.timeout), "gh", "pr", "checks", str(a.pr), "-R", fork, "--watch",
                    "--interval", "30"], capture_output=True, cwd=REPO_ROOT)
    checks = json.loads(sh("gh", "pr", "checks", str(a.pr), "-R", fork, "--json", "workflow,link,state",
                           check=False) or "[]")
    if any(c["state"] in ("PENDING", "QUEUED", "IN_PROGRESS") for c in checks):
        print(f"CI pending after {a.timeout}s")
        sys.exit(2)
    run_ids = {}
    for c in checks:
        m = re.search(r"/runs/(\d+)", c.get("link") or "")
        wf = file_of(c["workflow"])
        if m and wf:
            run_ids[wf] = int(m.group(1))
    if not run_ids:
        fail(f"no checks found on PR {a.pr}", code=3)
    verdict(run_ids, deadline, a.rerun_failed)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("workflows")
    w.add_argument("--branch", required=True)
    w.add_argument("--base", default="dev_agent")
    w.set_defaults(fn=cmd_workflows)
    for name, fn in (("run", cmd_run), ("pr", cmd_pr)):
        s = sub.add_parser(name)
        if name == "run":
            s.add_argument("--branch", required=True)
            s.add_argument("--base", default="dev_agent")
        else:
            s.add_argument("--pr", type=int, required=True)
        s.add_argument("--timeout", type=int, default=1500)
        s.add_argument("--no-rerun", dest="rerun_failed", action="store_false",
                       help="do not rerun failed jobs once before judging them")
        s.set_defaults(fn=fn)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

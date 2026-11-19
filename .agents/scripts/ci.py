#!/usr/bin/env python3
"""CI on an agent branch without a pull request. Usage:

  ci.py workflows --branch B [--base dev_agent]        list the workflows that apply to the branch's changes
  ci.py run --branch B [--base dev_agent] [--timeout 1500]
      dispatch those workflows on the pushed branch head (workflow_dispatch) and wait for them.
      exit 0 = all green, 1 = a run failed (failed run ids printed), 2 = still pending at timeout, 3 = error

Why: the fork's workflows trigger on `push: branches: '*'`, and `*` does not match the `/` in agent/... names, so a
push alone runs nothing. Each test workflow has `workflow_dispatch`; a workflow applies when it is active on the fork,
has a pull_request trigger, and its pull_request `paths` filter (if any) matches a changed file, as on a real PR.
"""
import argparse
import fnmatch
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, load_toml

REPO_ROOT = AGENTS_DIR.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
NAMES: dict = {}  # workflow file name -> display name (gh run list only reports the display name)


def sh(*cmd: str) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    if r.returncode:
        fail(f"{' '.join(cmd)}: {r.stderr.strip() or r.stdout.strip()}", code=3)
    return r.stdout


def fork() -> str:
    return load_toml("profile.toml")["project"]["fork"]


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


def applicable(branch: str, base: str) -> list:
    changed = [p for p in sh("git", "diff", "--name-only", f"{base}...{branch}").splitlines() if p]
    if not changed:
        fail(f"{branch} has no changes against {base}", code=3)
    listed = json.loads(sh("gh", "workflow", "list", "-R", fork(), "--all", "--json", "path,state,name"))
    active = {w["path"]: w["state"] for w in listed}
    NAMES.update({Path(w["path"]).name: w["name"] for w in listed})
    out = []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        rel = f".github/workflows/{wf.name}"
        on = triggers(wf.read_text())
        if "workflow_dispatch" not in on or "pull_request" not in on or active.get(rel) != "active":
            continue
        paths = on["pull_request"]
        if paths is None or any(fnmatch.fnmatch(c, p) for c in changed for p in paths):
            out.append(wf.name)
    return out


def cmd_workflows(a):
    for name in applicable(a.branch, a.base):
        print(name)


def cmd_run(a):
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
        sh("gh", "workflow", "run", name, "-R", fork(), "--ref", a.branch)
    print(f"dispatched on {a.branch} @ {head[:9]}: {', '.join(names)}")
    deadline = time.time() + a.timeout
    while True:
        time.sleep(30)
        runs = json.loads(sh("gh", "run", "list", "-R", fork(), "--branch", a.branch, "--event", "workflow_dispatch",
                             "--limit", "50", "--json", "databaseId,workflowName,status,conclusion,headSha,createdAt,url"))
        by_display = {NAMES[n]: n for n in names}
        latest = {}
        for r in runs:
            created = datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))
            name = by_display.get(r["workflowName"])
            if r["headSha"] == head and created >= since and name in names and name not in latest:
                latest[name] = r  # gh lists newest first
        done = {n: r for n, r in latest.items() if r["status"] == "completed"}
        if len(done) == len(names):
            bad = {n: r for n, r in done.items() if r["conclusion"] not in ("success", "skipped")}
            for n, r in sorted(done.items()):
                print(f"  {r['conclusion']:9} {n}  {r['url']}")
            if bad:
                print("CI red: " + ", ".join(f"{n} (gh run view {r['databaseId']} --log-failed -R {fork()})"
                                             for n, r in bad.items()))
                sys.exit(1)
            print("CI green")
            return
        if time.time() > deadline:
            waiting = sorted(set(names) - set(done))
            print(f"CI pending after {a.timeout}s: {', '.join(waiting)}")
            sys.exit(2)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("workflows", cmd_workflows), ("run", cmd_run)):
        s = sub.add_parser(name)
        s.add_argument("--branch", required=True)
        s.add_argument("--base", default="dev_agent")
        if name == "run":
            s.add_argument("--timeout", type=int, default=1500)
        s.set_defaults(fn=fn)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

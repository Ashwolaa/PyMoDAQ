#!/usr/bin/env python3
"""Deterministic scan of one scope: the only input the advisors get.

  scan.py <scope>            scope = package (pymodaq_utils) or package/slice (pymodaq_gui/plotting)
  scan.py <scope> --stdout   print instead of writing the file

Runs ruff (repo config), vulture, radon and jscpd on the scope's source and writes
`.agents/scans/<scope>-<tree>.md` (tree = git id of the scanned folder), then prints that path. The same source tree and the same tool versions give
the same file, byte for byte (the footer carries its sha256), so two runs can be checked to have seen identical
input. Coordinators pass the path to the advisors and add nothing of their own. A missing scanner is reported in
the file, never imitated. Standard library only; PATH comes from profile.toml [tools].env.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import AGENTS_DIR, fail, load_toml

REPO = AGENTS_DIR.parent
# ruff codes listed one by one (with location); everything else is style and only counted
BUG = re.compile(r"^(B\d|F(?!401|541)\d|E722|E9)")
IMPORTS = re.compile(r"^F401")
SIMPLIFY = re.compile(r"^(SIM|E741|E703|F541)")
VULTURE_FULL = 80          # vulture findings at or above this confidence are listed, the rest are counted
RADON_MIN_RANK = "C"


def apply_env(profile: dict) -> None:
    """Prepend the directories of `[tools].env` ("export PATH=a:b:$PATH") to PATH."""
    env = profile.get("tools", {}).get("env", "")
    m = re.match(r"\s*export\s+PATH=(.*)", env)
    if m:
        dirs = [os.path.expandvars(d) for d in m.group(1).strip().strip('"').split(":") if d and d != "$PATH"]
        os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])


def run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, **kw)


def version(tool: str) -> str:
    out = run([tool, "--version"]).stdout.strip().splitlines()
    return out[0].removeprefix(tool).strip() if out else "?"


def rel(p: str) -> str:
    try:
        return str(Path(p).resolve().relative_to(REPO))
    except ValueError:
        return p


def scope_path(profile: dict, scope: str) -> Path:
    pkg, _, slice_ = scope.partition("/")
    if pkg not in profile["scopes"]["order"]:
        fail(f"unknown scope {pkg!r}; expected one of {profile['scopes']['order']}")
    src = REPO / profile["scopes"]["src"].format(scope=pkg)
    path = src / slice_ if slice_ else src
    if not path.exists():
        fail(f"{rel(str(path))} does not exist")
    return path


def section_ruff(path: Path) -> list[str]:
    res = run(["ruff", "check", "--output-format", "json", "--no-fix", "--no-cache", str(path)])
    items = json.loads(res.stdout or "[]")
    rows = sorted((rel(i["filename"]), i["location"]["row"], i["code"] or "?", i["message"]) for i in items)
    out = [f"## ruff ({len(rows)} findings, repo config)"]
    for title, pat in (("Bug risk", BUG), ("Unused imports", IMPORTS), ("Simplifications", SIMPLIFY)):
        sel = [r for r in rows if pat.match(r[2])]
        out.append(f"### {title} ({len(sel)})")
        out += [f"- {f}:{line} {code} {msg}" for f, line, code, msg in sel] or ["- none"]
    style = [r for r in rows if not (BUG.match(r[2]) or IMPORTS.match(r[2]) or SIMPLIFY.match(r[2]))]
    out.append(f"### Style, counted only ({len(style)}; per rule: findings / files)")
    per_rule = defaultdict(set)
    for f, _, code, _ in style:
        per_rule[code].add(f)
    counts = Counter(r[2] for r in style)
    out += [f"- {code}: {counts[code]} / {len(per_rule[code])}" for code in sorted(counts)] or ["- none"]
    return out


def section_vulture(path: Path) -> list[str]:
    res = run(["vulture", str(path), "--min-confidence", "60"])
    rows = []
    for line in res.stdout.splitlines():
        m = re.match(r"(.+?):(\d+): (.+) \((\d+)% confidence\)", line)
        if m:
            rows.append((rel(m[1]), int(m[2]), m[3], int(m[4])))
    rows.sort()
    full = [r for r in rows if r[3] >= VULTURE_FULL]
    low = Counter(r[0] for r in rows if r[3] < VULTURE_FULL)
    out = [f"## vulture ({len(rows)} findings at >= 60% confidence)",
           f"### >= {VULTURE_FULL}% confidence ({len(full)})"]
    out += [f"- {f}:{line} {msg} ({c}%)" for f, line, msg, c in full] or ["- none"]
    out.append(f"### 60-{VULTURE_FULL - 1}% confidence, counted per file (mostly public API seen as unused)")
    out += [f"- {f}: {n}" for f, n in sorted(low.items())] or ["- none"]
    return out


def section_radon(path: Path) -> list[str]:
    res = run(["radon", "cc", "-s", "-n", RADON_MIN_RANK, "-j", str(path)])
    data = json.loads(res.stdout or "{}")
    rows = []
    for f, blocks in data.items():
        for b in blocks if isinstance(blocks, list) else []:
            name = f"{b['classname']}.{b['name']}" if b.get("classname") else b["name"]
            rows.append((-b["complexity"], rel(f), b["lineno"], name, b["rank"]))
    rows.sort()
    out = [f"## radon cyclomatic complexity, rank {RADON_MIN_RANK} or worse ({len(rows)})"]
    out += [f"- {f}:{line} {name} {rank}({-c})" for c, f, line, name, rank in rows] or ["- none"]
    return out


def section_jscpd(path: Path) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        run(["jscpd", "--silent", "-a", "-r", "json", "-o", tmp, str(path)])
        report = Path(tmp) / "jscpd-report.json"
        if not report.exists():
            return ["## jscpd", "- no report produced"]
        data = json.loads(report.read_text())
    total = data["statistics"]["total"]
    dups = sorted((-d["lines"], rel(d["firstFile"]["name"]), d["firstFile"]["start"], d["firstFile"]["end"],
                   rel(d["secondFile"]["name"]), d["secondFile"]["start"], d["secondFile"]["end"])
                  for d in data["duplicates"])
    out = [f"## jscpd duplication: {total['percentage']:.2f}% of lines, {total['clones']} clones"]
    out += [f"- {f1}:{s1}-{e1} = {f2}:{s2}-{e2} ({-n} lines)" for n, f1, s1, e1, f2, s2, e2 in dups] or ["- none"]
    return out


SECTIONS = (("ruff", section_ruff), ("vulture", section_vulture), ("radon", section_radon), ("jscpd", section_jscpd))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("scope")
    ap.add_argument("--stdout", action="store_true")
    a = ap.parse_args()
    profile = load_toml("profile.toml")
    apply_env(profile)
    path = scope_path(profile, a.scope)
    commit = run(["git", "rev-parse", "--short=9", "HEAD"]).stdout.strip()
    # content address of the scanned folder: unchanged source -> same tree id -> same file and hash
    tree = run(["git", "rev-parse", "--short=12", f"HEAD:{rel(str(path))}"]).stdout.strip()
    dirty = bool(run(["git", "status", "--porcelain", "--", str(path)]).stdout.strip())
    tools = {name: (version(name) if shutil.which(name) else None) for name, _ in SECTIONS}
    body = [f"# Scan: {a.scope}", f"path: {rel(str(path))}   tree: {tree}{' + uncommitted changes' if dirty else ''}",
            "tools: " + ", ".join(f"{k} {v}" if v else f"{k} MISSING" for k, v in tools.items()), ""]
    for name, fn in SECTIONS:
        body += (fn(path) if tools[name] else [f"## {name}", "- MISSING: not installed, not imitated"]) + [""]
    text = "\n".join(body)
    text += f"sha256: {hashlib.sha256(text.encode()).hexdigest()[:16]}\n"
    text += f"(scanned at commit {commit}; not part of the hash)\n"
    if a.stdout:
        print(text, end="")
        return
    out = AGENTS_DIR / "scans" / f"{a.scope.replace('/', '__')}-{tree}{'-dirty' if dirty else ''}.md"
    out.parent.mkdir(exist_ok=True)
    hashed = text.rsplit("(scanned at commit", 1)[0]
    if not (out.exists() and out.read_text().rsplit("(scanned at commit", 1)[0] == hashed):
        out.write_text(text)  # same source and tools as an existing scan: keep that file untouched
    print(rel(str(out)))
    if not any(tools.values()):
        sys.exit(3)  # nothing could be scanned: the caller logs --outcome failed


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PreToolUse hook (Bash): hard stop for anything that would reach upstream, whatever an agent was told.

Blocks (exit 2, reason on stderr, which Claude Code shows the agent):
  - `git push` naming the upstream remote, or pushing to the `dev` mirror branch;
  - any `gh` command whose -R/--repo is not the fork, and `gh api` writes to the upstream repository;
  - direct `gh pr create` / `gh pr merge`: scripts/merge.py opens and merges PRs, after its checks.
Names come from .agents/profile.toml ([project] fork, upstream, mirror_branch). Scripts that run git/gh as
subprocesses are not seen by this hook; they take the fork from the same profile.
"""
import json
import os
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None


def profile():
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
    try:
        return tomllib.loads((root / ".agents" / "profile.toml").read_text())["project"]
    except Exception:
        return {}


def problems(cmd: str) -> list:
    p = profile()
    fork = p.get("fork", "Ashwolaa/PyMoDAQ")
    upstream = p.get("upstream", "PyMoDAQ/PyMoDAQ")
    mirror = p.get("mirror_branch", "dev")
    out = []
    for seg in re.split(r"&&|\|\||[;|\n]", cmd):
        s = seg.strip()
        if re.search(r"\bgit\b.*\bpush\b", s):
            if re.search(r"\bupstream\b", s):
                out.append("git push to the upstream remote")
            if re.search(rf"(?:^|\s|:)(?:refs/heads/)?{re.escape(mirror)}(?=\s|$)", s.split("push", 1)[1]):
                out.append(f"git push to the `{mirror}` mirror branch (only sync_branches.sh fast-forwards it)")
        if re.search(r"\bgh\b", s):
            for repo in re.findall(r"(?:\s-R|\s--repo)(?:\s+|=)['\"]?([\w.-]+/[\w.-]+)", s):
                if repo.lower() != fork.lower():
                    out.append(f"gh on {repo}: agents only use the fork {fork}")
            if re.search(r"\bgh\s+pr\s+(create|merge)\b", s):
                out.append("direct `gh pr create/merge`: scripts/merge.py opens and merges PRs after its checks")
            if re.search(r"\bgh\s+api\b", s) and upstream.lower() in s.lower() \
                    and re.search(r"(-X|--method)\s*(POST|PUT|PATCH|DELETE)|\s-f\s|\s-F\s|--field|--input", s, re.I):
                out.append(f"gh api write to {upstream}")
    return out


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    cmd = (data.get("tool_input") or {}).get("command") or ""
    found = problems(cmd)
    if found:
        print("Blocked by .claude/hooks/guard_upstream.py: " + "; ".join(dict.fromkeys(found))
              + ". Upstream work needs the owner's explicit go (rules.md 2).", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

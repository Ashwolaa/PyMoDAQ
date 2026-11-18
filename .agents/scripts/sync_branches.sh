#!/usr/bin/env bash
# Keep `dev` a pure mirror of upstream/dev and merge it into `dev_agent` (merge commit, no history rewrite).
# Usage: sync_branches.sh [--dry-run]. Needs remotes: `upstream` (PyMoDAQ/PyMoDAQ) and `origin` (the fork).
# Run it from a clean worktree dedicated to dev_agent (e.g. ../PyMoDAQ-dev-agent), not from a feature worktree.
set -euo pipefail
dry=0; [ "${1:-}" = "--dry-run" ] && dry=1
run() { echo "+ $*"; [ $dry -eq 1 ] || "$@"; }

git remote get-url upstream >/dev/null 2>&1 || { echo "remote 'upstream' missing" >&2; exit 2; }
git remote get-url origin   >/dev/null 2>&1 || { echo "remote 'origin' missing" >&2; exit 2; }
[ -z "$(git status --porcelain)" ] || { echo "working tree not clean" >&2; exit 2; }

run git fetch upstream dev
run git fetch origin
# dev: fast-forward only, never receives agent commits. Updated without a checkout, so the script can run
# from the dev_agent worktree; a plain (non-force) push refuses anything but a fast-forward on the fork.
git merge-base --is-ancestor dev upstream/dev || { echo "local dev has diverged from upstream/dev" >&2; exit 2; }
run git branch -f dev upstream/dev
run git push origin upstream/dev:refs/heads/dev
# dev_agent: create from dev if missing, then merge dev into it
if ! git show-ref --verify --quiet refs/heads/dev_agent; then
  if git show-ref --verify --quiet refs/remotes/origin/dev_agent; then
    run git checkout -b dev_agent origin/dev_agent
  else
    run git checkout -b dev_agent dev
  fi
else
  run git checkout dev_agent
fi
run git merge --no-edit dev
run git push -u origin dev_agent

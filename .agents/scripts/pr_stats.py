#!/usr/bin/env python3
"""PR size versus time-to-merge, to set `[limits].pr_max_changed_lines` from data instead of a guess.

  pr_stats.py [--repo OWNER/NAME] [--label agent-made] [--author LOGIN] [--limit 400] [--keep-mechanical]

Reads merged PRs with `gh` (must be authenticated). Merge/backport/release/bump PRs are dropped by default: they are
large for mechanical reasons. Time-to-merge is wall-clock from creation to merge, so self-merged PRs make it look
faster than review really is; compare --author and --label subsets before drawing a conclusion.
"""
import argparse
import json
import statistics
import subprocess
from datetime import datetime

BINS = ((0, 50), (50, 150), (150, 300), (300, 600), (600, 1500), (1500, None))
MECHANICAL = ("merge", "backport", "release", "bump")


def hours(p) -> float:
    t = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))  # noqa: E731
    return (t(p["mergedAt"]) - t(p["createdAt"])).total_seconds() / 3600


def q(values, f):
    return values[min(len(values) - 1, int(f * len(values)))]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default="PyMoDAQ/PyMoDAQ")
    ap.add_argument("--label")
    ap.add_argument("--author")
    ap.add_argument("--limit", type=int, default=400)
    ap.add_argument("--keep-mechanical", action="store_true")
    a = ap.parse_args()
    cmd = ["gh", "pr", "list", "-R", a.repo, "--state", "merged", "--limit", str(a.limit), "--json",
           "number,additions,deletions,changedFiles,createdAt,mergedAt,author,title"]
    if a.label:
        cmd += ["--label", a.label]
    if a.author:
        cmd += ["--author", a.author]
    prs = json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)
    if not a.keep_mechanical:
        prs = [p for p in prs if not any(w in p["title"].lower() for w in MECHANICAL)]
    if not prs:
        print("no merged PRs match")
        return
    size = lambda p: p["additions"] + p["deletions"]  # noqa: E731
    sizes = sorted(map(size, prs))
    span = sorted(p["mergedAt"][:10] for p in prs)
    print(f"{a.repo}: {len(prs)} merged PRs, {span[0]} .. {span[-1]}")
    print(f"changed lines: p25={q(sizes, .25)} median={q(sizes, .5)} p75={q(sizes, .75)} p90={q(sizes, .9)}")
    print(f"{'lines':>11} {'PRs':>5} {'median h':>9} {'p75 h':>8} {'median files':>13}")
    for lo, hi in BINS:
        b = [p for p in prs if size(p) >= lo and (hi is None or size(p) < hi)]
        if not b:
            continue
        t = sorted(map(hours, b))
        files = statistics.median(p["changedFiles"] for p in b)
        print(f"{lo:>5}-{hi or '':<5} {len(b):>5} {statistics.median(t):>9.1f} {q(t, .75):>8.1f} {files:>13}")
    authors = {}
    for p in prs:
        authors[p["author"]["login"]] = authors.get(p["author"]["login"], 0) + 1
    print("authors: " + ", ".join(f"{k} {v}" for k, v in sorted(authors.items(), key=lambda kv: -kv[1])[:6]))


if __name__ == "__main__":
    main()

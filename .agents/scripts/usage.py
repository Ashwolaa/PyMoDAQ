#!/usr/bin/env python3
"""Measure Claude Code usage from the local session transcripts (no guessing).

  usage.py tokens [--session ID|current] [--since ISO] [--until ISO] [--by model|agent|tool|session] [--json]
  usage.py snapshots [--since ISO]      /usage readings and limit hits found in the transcripts
  usage.py calibrate                    tokens spent between two /usage readings of the same window

Sources: ~/.claude/projects/*/<session>.jsonl and <session>/subagents/agent-*.jsonl (+ .meta.json for the agent
type). Every project is read, because the plan quota is shared by the whole account. Each API request is counted
once (a transcript repeats its usage on every content block). Cloud sessions and claude.ai chats leave no local
transcript: they still consume the quota but are invisible here, so calibrate on a quiet window.

`current` means $CLAUDE_CODE_SESSION_ID. The plan quota is not a plain token count (models and cache reads weigh
differently), so token classes are reported separately and calibration is done against /usage readings.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CLASSES = ("input", "cache_write", "cache_read", "output")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
RE_SESSION = re.compile(r"Current session: (\d+)% used · resets ([^\n<]+)")
RE_WEEK = re.compile(r"Current week \(([^)]+)\): (\d+)% used · resets ([^\n<]+)")
RE_LIMIT = re.compile(r"You've hit your (\w+) limit · resets ([^\n\"<]+)")


def projects_dir() -> Path:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "projects"


def parse_ts(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def transcripts(session: str | None):
    """Yield (path, session_id, agent_label) for every transcript, main sessions and sub-agents."""
    for proj in sorted(projects_dir().glob("*")):
        if not proj.is_dir():
            continue
        for main in proj.glob("*.jsonl"):
            sid = main.stem
            if session and sid != session:
                continue
            yield main, sid, "main"
            for sub in sorted((proj / sid / "subagents").glob("agent-*.jsonl")):
                meta = sub.with_suffix(".meta.json")
                label = "subagent"
                if meta.exists():
                    try:
                        label = json.loads(meta.read_text()).get("agentType") or label
                    except (OSError, json.JSONDecodeError):
                        pass
                yield sub, sid, label


def requests(session=None, since=None, until=None):
    """One record per unique API request inside the time window."""
    seen = set()
    for path, sid, agent in transcripts(session):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"usage"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = d.get("message")
                if d.get("type") != "assistant" or not isinstance(msg, dict) or not msg.get("usage"):
                    continue
                model = msg.get("model") or "?"
                if model.startswith("<"):  # synthetic messages (limit notices, errors) cost nothing
                    continue
                ts = parse_ts(d["timestamp"])
                if (since and ts < since) or (until and ts > until):
                    continue
                key = d.get("requestId") or msg.get("id") or d.get("uuid")
                tools = [c.get("name") for c in msg.get("content") or [] if c.get("type") == "tool_use"]
                if key in seen:
                    # same request, another content block: only collect its tool calls
                    if tools:
                        yield {"dup": True, "tools": tools, "session": sid, "agent": agent, "model": model, "ts": ts,
                               "transcript": path.name}
                    continue
                seen.add(key)
                u = msg["usage"]
                yield {
                    "dup": False, "session": sid, "agent": agent, "model": model, "ts": ts, "tools": tools,
                    "transcript": path.name,
                    "input": u.get("input_tokens") or 0,
                    "cache_write": u.get("cache_creation_input_tokens") or 0,
                    "cache_read": u.get("cache_read_input_tokens") or 0,
                    "output": u.get("output_tokens") or 0,
                }


def aggregate(rows, by=None):
    groups = defaultdict(lambda: {**{c: 0 for c in CLASSES}, "requests": 0, "tool_calls": 0,
                                  "first": None, "last": None})
    for r in rows:
        keys = r["tools"] if by == "tool" else [r.get(by, "total") if by else "total"]
        for k in keys or []:
            g = groups[k]
            if by == "tool":
                g["tool_calls"] += 1
                continue
            g["tool_calls"] += len(r["tools"])
            if r["dup"]:
                continue
            g["requests"] += 1
            for c in CLASSES:
                g[c] += r[c]
            g["first"] = min(g["first"] or r["ts"], r["ts"])
            g["last"] = max(g["last"] or r["ts"], r["ts"])
    for g in groups.values():
        g["minutes"] = round((g["last"] - g["first"]).total_seconds() / 60, 1) if g["first"] else 0
        g["first"] = g["first"].isoformat() if g["first"] else None
        g["last"] = g["last"].isoformat() if g["last"] else None
    return dict(groups)


def resolve_session(s):
    if s == "current":
        s = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if not s:
            sys.exit("CLAUDE_CODE_SESSION_ID is not set: pass --session <id>")
    return s


def cmd_tokens(a):
    rows = requests(resolve_session(a.session), a.since, a.until)
    if a.by != "tool":
        rows = (r for r in rows if not r["dup"] or r["tools"])
    res = aggregate(rows, a.by)
    if a.json:
        print(json.dumps(res, indent=1, sort_keys=True))
        return
    if not res:
        print("no requests in that window")
        return
    if a.by == "tool":
        for k, g in sorted(res.items(), key=lambda kv: -kv[1]["tool_calls"]):
            print(f"{k:<28} {g['tool_calls']:>6} calls")
        return
    print(f"{'group':<38} {'req':>5} {'input':>9} {'cache_w':>10} {'cache_r':>12} {'output':>9} {'tools':>6} {'span_min':>9}")
    for k, g in sorted(res.items(), key=lambda kv: -kv[1]["output"]):
        print(f"{str(k)[:38]:<38} {g['requests']:>5} {g['input']:>9} {g['cache_write']:>10} {g['cache_read']:>12} "
              f"{g['output']:>9} {g['tool_calls']:>6} {g['minutes']:>9}")


def snapshots(since=None):
    out, seen = [], set()
    for path, sid, _ in transcripts(None):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if "% used" not in line and "hit your" not in line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if d.get("type") not in ("system", "assistant", "user") or "timestamp" not in d:
                    continue
                text = _text(d)
                ts = parse_ts(d["timestamp"])
                if since and ts < since:
                    continue
                snap = {"ts": ts, "session": sid}
                if m := RE_SESSION.search(text):
                    snap["session_pct"], snap["session_reset"] = int(m[1]), m[2].strip()
                weeks = {w[0]: (int(w[1]), w[2].strip()) for w in RE_WEEK.findall(text)}
                if "all models" in weeks:
                    snap["week_pct"], snap["week_reset"] = weeks["all models"]
                if d.get("type") == "assistant" and (m := RE_LIMIT.search(text)):
                    snap["limit"], snap["limit_reset"] = m[1], m[2].strip()
                if len(snap) == 2:
                    continue
                key = (d["timestamp"], snap.get("week_pct"), snap.get("limit"))
                if key not in seen:
                    seen.add(key)
                    out.append(snap)
    return sorted(out, key=lambda s: s["ts"])


def _text(d) -> str:
    """Plain text of a record: system content, or the text blocks of a message."""
    c = d.get("content")
    if c is None:
        c = (d.get("message") or {}).get("content")
    if isinstance(c, list):
        c = "\n".join(b.get("text", "") for b in c if isinstance(b, dict))
    return ANSI.sub("", c if isinstance(c, str) else "")


def cmd_snapshots(a):
    snaps = snapshots(a.since)
    if not snaps:
        print("no /usage readings or limit hits found")
    for s in snaps:
        if "limit" in s:
            print(f"{s['ts'].isoformat()}  LIMIT {s['limit']} hit, resets {s['limit_reset']}")
        else:
            print(f"{s['ts'].isoformat()}  session {s.get('session_pct', '?')}% (resets {s.get('session_reset', '?')})"
                  f"  week {s.get('week_pct', '?')}% (resets {s.get('week_reset', '?')})")


def cmd_calibrate(a):
    snaps = [s for s in snapshots() if "week_pct" in s]
    pairs = [(x, y) for x, y in zip(snaps, snaps[1:]) if x["week_reset"] == y["week_reset"]]
    if not pairs:
        print(f"{len(snaps)} /usage reading(s), no two in the same weekly window: run /usage before and after a "
              "measured run (nothing else using the plan in between).")
        return
    for x, y in pairs:
        tot = aggregate(r for r in requests(None, x["ts"], y["ts"]) if not r["dup"]).get("total")
        dw = y["week_pct"] - x["week_pct"]
        same_s = x.get("session_reset") == y.get("session_reset")
        ds = (y.get("session_pct", 0) - x.get("session_pct", 0)) if same_s else None
        print(f"{x['ts'].isoformat()} -> {y['ts'].isoformat()}: week +{dw}%"
              + (f", session +{ds}%" if ds is not None else ", session window reset in between"))
        if tot:
            print("   " + ", ".join(f"{c}={tot[c]}" for c in CLASSES) + f", requests={tot['requests']}")
            if dw > 0:
                print(f"   ~{tot['output'] // dw} output tokens per week-% "
                      f"(~{(tot['input'] + tot['cache_write']) // dw} uncached input tokens per week-%)")
        else:
            print("   no local requests in between (usage came from elsewhere)")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("tokens")
    t.add_argument("--session", default=None, help="session id or 'current'")
    t.add_argument("--since", type=parse_ts)
    t.add_argument("--until", type=parse_ts)
    t.add_argument("--by", choices=("model", "agent", "tool", "session"), default=None)
    t.add_argument("--json", action="store_true")
    t.set_defaults(fn=cmd_tokens)
    s = sub.add_parser("snapshots")
    s.add_argument("--since", type=parse_ts)
    s.set_defaults(fn=cmd_snapshots)
    c = sub.add_parser("calibrate")
    c.set_defaults(fn=cmd_calibrate)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()

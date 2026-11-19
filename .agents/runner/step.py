#!/usr/bin/env python3
"""Run one headless Claude Code step and stop it at its first final result. Usage:

  step.py --out FILE [--model sonnet] -- "<prompt>"
  exit 0 = the step ended normally, 1 = it ended with an error, 3 = a usage limit was hit, 2 = no result (crash/timeout)

Why: a headless session keeps waiting for work it started in the background (a sub-agent, a long Bash call). When that
work ends after the step's final report, the session wakes up and runs a second pass (seen three times on 2026-11-19:
duplicate ledger lines, an extra plan run). Reading `--output-format stream-json` and killing the whole process group
at the first `result` event makes every step exactly one pass. Stray background work dies with it, by design.
The assistant's text and the final result go to FILE; one JSON summary line is printed on stdout.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time

TOOLS = ["Bash", "Read", "Grep", "Glob", "Write", "Edit", "Agent"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--timeout", type=int, default=4 * 3600, help="hard stop for one step, seconds")
    p.add_argument("prompt")
    a = p.parse_args()
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_CHILD_SESSION")}
    cmd = ["claude", "-p", "--model", a.model, "--permission-mode", "acceptEdits", "--output-format", "stream-json",
           "--verbose", "--allowedTools", *TOOLS, "--", a.prompt]
    started = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
                            start_new_session=True)
    result, session, limit = None, None, False
    with open(a.out, "w") as out:
        out.write(f"$ step.py --model {a.model} -- {a.prompt}\n\n")
        for line in proc.stdout:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                out.write(line)
                continue
            session = d.get("session_id") or session
            if d.get("type") == "assistant":
                for c in (d.get("message") or {}).get("content") or []:
                    if c.get("type") == "text" and c.get("text", "").strip():
                        out.write(c["text"].strip() + "\n\n")
            elif d.get("type") == "result":
                result = d
                text = d.get("result") or ""
                out.write("=== result ===\n" + text + "\n")
                limit = "limit" in text.lower() and ("hit your" in text.lower() or "usage limit" in text.lower())
                break  # one pass only: stop before a late notification can wake the session up
            if time.time() - started > a.timeout:
                out.write(f"=== step timeout after {a.timeout}s ===\n")
                break
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=15)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    summary = {"session": session, "minutes": round((time.time() - started) / 60, 1),
               "subtype": (result or {}).get("subtype"), "is_error": (result or {}).get("is_error"),
               "turns": (result or {}).get("num_turns"), "limit": limit}
    print(json.dumps(summary))
    sys.exit(3 if limit else 2 if result is None else 1 if result.get("is_error") else 0)


if __name__ == "__main__":
    main()

"""What a session really did, read from its transcripts: the proof task.py and merge.py ask for (rules.md 16)."""
import json
from collections import Counter

import usage

EDIT_TOOLS = ("Edit", "Write", "NotebookEdit")


def launches(session, since) -> Counter:
    """Sub-agent launches by agent type in this session since `since` (one transcript per launch)."""
    since = usage.parse_ts(since) if isinstance(since, str) else since
    seen = {(r["agent"], r["transcript"]) for r in usage.requests(session, since) if r["agent"] != "main"}
    return Counter(agent for agent, _ in seen)


def specialist_launched(session, since) -> bool:
    return any(a.startswith("spec-") or a == "test-agent" for a in launches(session, since))


def coordinator_edits(session, since, repo, allowed=("/.agents/",)) -> list:
    """Files under `repo` the main session edited with a file tool since `since`, except state paths."""
    since = usage.parse_ts(since) if isinstance(since, str) else since
    out = []
    for path, sid, agent in usage.transcripts(session):
        if agent != "main":
            continue
        for line in open(path, encoding="utf-8", errors="replace"):
            if '"tool_use"' not in line or '"file_path"' not in line:
                continue
            d = json.loads(line)
            if usage.parse_ts(d.get("timestamp", "1970-01-01T00:00:00Z")) < since:
                continue
            for c in (d.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use" and c.get("name") in EDIT_TOOLS:
                    fp = (c.get("input") or {}).get("file_path", "")
                    if fp.startswith(str(repo)) and not any(a in fp for a in allowed):
                        out.append(fp)
    return out

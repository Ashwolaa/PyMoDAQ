"""Shared helpers for the .agents scripts (standard library only)."""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore

AGENTS_DIR = Path(__file__).resolve().parent.parent


def load_toml(name: str) -> dict:
    with open(AGENTS_DIR / name, "rb") as f:
        return tomllib.load(f)


def read_jsonl(name: str) -> list:
    path = AGENTS_DIR / name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(name: str, record: dict) -> None:
    with open(AGENTS_DIR / name, "a") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def today() -> str:
    return date.today().isoformat()


def require_state_branch() -> None:
    """State files (.agents/) are committed only on the integration branch, never on agent/* branches."""
    try:
        branch = subprocess.run(["git", "-C", str(AGENTS_DIR), "branch", "--show-current"],
                                capture_output=True, text=True).stdout.strip()
    except OSError:
        return
    integration = load_toml("profile.toml").get("project", {}).get("integration_branch", "dev_agent")
    if branch and branch != integration:
        fail(f"state files live on {integration!r}, you are on {branch!r}: run `git switch {integration}` first")


def fail(msg: str, code: int = 2):
    print(msg, file=sys.stderr)
    sys.exit(code)

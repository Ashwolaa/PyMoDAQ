"""Tests of the .agents tooling. Run from the worktree root: `pytest .agents/tests` (under the profile's [tools].env).
They only read the state files; anything they write goes to pytest's tmp_path."""
import subprocess
import sys
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AGENTS / "scripts"))
sys.path.insert(0, str(AGENTS / "runner"))


@pytest.fixture
def repo(tmp_path):
    """A throwaway git repository with one committed file."""
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (tmp_path / "a.txt").write_text("a\n")
    run("add", "a.txt")
    run("commit", "-q", "-m", "init")
    return tmp_path

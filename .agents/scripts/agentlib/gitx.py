"""Running git and other commands from the scripts."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def run(cmd, check=True, cwd=None, shell=False, code=2) -> subprocess.CompletedProcess:
    """Run a command; on failure (check=True) print its error and exit with `code`."""
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or REPO, shell=shell,
                       executable="/bin/bash" if shell else None)
    if check and r.returncode:
        shown = cmd if shell else " ".join(map(str, cmd))
        print(f"{shown}: {(r.stderr or r.stdout).strip()[-800:]}", file=sys.stderr)
        sys.exit(code)
    return r


def git(*args, check=True, cwd=None) -> str:
    """git output with surrounding white space removed. Never use it for `status --porcelain`: see porcelain()."""
    return run(["git", *args], check=check, cwd=cwd).stdout.strip()


def porcelain(*paths, cwd=None) -> list:
    """[(XY, path)] from `git status --porcelain`, read unstripped: its first column is often a space
    (' M file'), and stripping the whole output shifts the first line (task.py close, 2026-11-19)."""
    out = run(["git", "status", "--porcelain", "--", *paths] if paths else ["git", "status", "--porcelain"],
              cwd=cwd).stdout
    return [(line[:2], line[3:]) for line in out.splitlines() if line]


def dirty(*paths, cwd=None) -> bool:
    return bool(porcelain(*paths, cwd=cwd))


def toplevel(*paths) -> list:
    """Pathspecs from the repository root, whatever the cwd (`git -C .agents diff -- packages` silently means
    .agents/packages; status.py, 2026-11-19)."""
    return [f":/{p}" for p in paths]


def branch(cwd=None) -> str:
    return git("branch", "--show-current", cwd=cwd)


def head(ref="HEAD", cwd=None) -> str:
    return git("rev-parse", ref, cwd=cwd)


def remote_head(ref, remote="origin", cwd=None):
    out = git("ls-remote", remote, f"refs/heads/{ref}", cwd=cwd).split()
    return out[0] if out else None

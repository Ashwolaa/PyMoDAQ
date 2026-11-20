"""Plan files (`.agents/plans/*.md`): task blocks, their fields and statuses, and the package each task belongs to.

A task block starts with `## T-<...> <title>` and runs to the next `## ` heading. Its lines look like
`- scope: pymodaq_utils   specialty: refactor (bug fix)   risk: medium` and `- status: <text>`. Experiment plans in
`plans/experiments/` are never read by commands.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

from _common import AGENTS_DIR, fail, load_toml

PLANS = AGENTS_DIR / "plans"
REPO = AGENTS_DIR.parent
STATUSES = ("proposed", "approved", "done", "blocked", "expired")
_HEAD = re.compile(r"^## (T-[\w.-]+)[ \t]*(.*)$", re.M)


@dataclass
class Task:
    id: str
    title: str
    plan: Path              # absolute path of the plan file
    block: str              # the whole block, heading included
    fields: dict = field(default_factory=dict)

    @property
    def status(self) -> str:
        return self.fields.get("status", "")

    @property
    def plan_rel(self) -> str:
        return str(self.plan.relative_to(REPO)) if self.plan.is_relative_to(REPO) else str(self.plan)

    def get(self, name, default=None):
        """First token of a field (`risk`, `scope`, `specialty`), e.g. 'refactor' for 'refactor (bug fix)'."""
        m = re.search(rf"\b{re.escape(name)}:\s*([\w.-]+)", self.block)
        return m.group(1) if m else default


def _fields(block: str) -> dict:
    out = {}
    for line in block.splitlines():
        m = re.match(r"^- (status|verdicts|finding|files|constraints|note|tests):\s*(.*)$", line)
        if m:
            out.setdefault(m.group(1), m.group(2).strip())
    return out


def parse(path) -> list:
    """Every task of one plan file, in file order."""
    path = Path(path)
    text = path.read_text()
    heads = list(_HEAD.finditer(text))
    nxt = [m.start() for m in re.finditer(r"^## ", text, re.M)]
    tasks = []
    for m in heads:
        end = next((n for n in nxt if n > m.start()), len(text))
        block = text[m.start():end]
        tasks.append(Task(m.group(1), m.group(2).strip(), path, block, _fields(block)))
    return tasks


def plan_files():
    return [p for p in sorted(PLANS.glob("*.md")) if not p.name.startswith("_")]


def all_tasks() -> list:
    return [t for p in plan_files() for t in parse(p)]


def find(task_id, plan=None):
    """The task with this id, from `plan` if given, else from the first plan file that has it."""
    for p in ([resolve(plan)] if plan else plan_files()):
        for t in parse(p):
            if t.id == task_id:
                return t
    return None


def resolve(plan) -> Path:
    p = Path(plan)
    for cand in (p, REPO / p, PLANS / p):
        if cand.exists():
            return cand.resolve()
    fail(f"plan not found: {plan}")


def set_status(plan, task_id, status: str) -> None:
    """The only way a plan status changes (rules.md 13)."""
    word = status.split()[0].rstrip("—-:(") if status.strip() else ""
    if word not in STATUSES:
        fail(f"status must start with one of {STATUSES}")
    path = resolve(plan)
    text = path.read_text()
    for t in parse(path):
        if t.id == task_id:
            new, n = re.subn(r"^- status:.*$", lambda _: f"- status: {status}", t.block, count=1, flags=re.M)
            if not n:
                fail(f"{task_id} has no '- status:' line")
            start = text.index(t.block)
            path.write_text(text[:start] + new + text[start + len(t.block):])
            return
    fail(f"{task_id} not found in {path.name}")


def package_of(task) -> str:
    """The package a task belongs to, for state paths (rules.md 19): its `scope` if that is a package, else the
    first package its `files` name, else the package in the plan's file name. T-010 had `scope: docs`."""
    order = load_toml("profile.toml")["scopes"]["order"]
    scope = task.get("scope")
    if scope in order:
        return scope
    for pkg in re.findall(r"packages/([\w]+)/", task.block):
        if pkg in order:
            return pkg
    m = re.match(r"\d{4}-\d{2}-\d{2}-([a-z_]+?)(?:-[\w-]+)?\.md$", task.plan.name)
    if m and m.group(1) in order:
        return m.group(1)
    return scope or "repo"

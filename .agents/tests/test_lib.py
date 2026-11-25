"""agentlib: git, plans, reports. Regression cases are named after the bug they pin."""
import textwrap

import pytest

from agentlib import gitx, plans, reports


# ---------------------------------------------------------------- gitx
def test_porcelain_keeps_first_line_column(repo):
    """task.py close, 2026-11-19: stripping `git status --porcelain` turned ' M .agents/x' into 'M .agents/x',
    so path[3:] lost its first character and the handoff looked like a product file."""
    (repo / "a.txt").write_text("changed\n")
    (repo / "b.txt").write_text("new\n")
    entries = gitx.porcelain(cwd=repo)
    assert (" M", "a.txt") in entries
    assert ("??", "b.txt") in entries
    assert gitx.dirty("a.txt", cwd=repo)


def test_toplevel_pathspecs():
    """status.py, 2026-11-19: `git -C .agents diff -- packages` meant .agents/packages."""
    assert gitx.toplevel("packages", "docs") == [":/packages", ":/docs"]


# ---------------------------------------------------------------- plans
PLAN = textwrap.dedent("""\
    # Plan: pymodaq_utils — test
    ## T-pymodaq_utils-101 Fix a thing
    - scope: pymodaq_utils   specialty: refactor (bug fix)   risk: medium
    - files: packages/pymodaq_utils/src/pymodaq_utils/x.py:1
    - verdicts: decider-compat-risk: approve — ok; decider-test-change: approve — ok
    - status: approved

    ## T-pymodaq_utils-102 Docs table
    - scope: docs   specialty: docs   risk: low
    - files: docs/src/developer_folder/instrument_plugins.rst:144
    - status: proposed (touches docs)
    """)


@pytest.fixture
def plan(tmp_path):
    p = tmp_path / "2026-11-20-pymodaq_utils-test.md"
    p.write_text(PLAN)
    return p


def test_parse_fields(plan):
    t1, t2 = plans.parse(plan)
    assert (t1.id, t1.title, t1.status) == ("T-pymodaq_utils-101", "Fix a thing", "approved")
    assert t1.get("specialty") == "refactor" and t1.get("risk") == "medium"
    assert t2.status.startswith("proposed")
    assert "T-pymodaq_utils-102" not in t1.block


def test_package_of_scope_docs(plan):
    """T-010, 2026-11-20: `scope: docs` sent the handoff to handoff/docs.md; the package comes from the plan name."""
    t1, t2 = plans.parse(plan)
    assert plans.package_of(t1) == "pymodaq_utils"
    assert plans.package_of(t2) == "pymodaq_utils"


def test_set_status_only_that_task(plan):
    plans.set_status(plan, "T-pymodaq_utils-102", "done — PR #15 merged (auto: low risk)")
    t1, t2 = plans.parse(plan)
    assert t2.status == "done — PR #15 merged (auto: low risk)"
    assert t1.status == "approved"


def test_set_status_rejects_unknown_word(plan):
    with pytest.raises(SystemExit):
        plans.set_status(plan, "T-pymodaq_utils-101", "finished")


def test_real_plans_parse():
    tasks = plans.all_tasks()
    assert len(tasks) >= 12
    assert all(t.status.split()[0].rstrip("—-:(") in plans.STATUSES for t in tasks)
    assert plans.find("T-pymodaq_utils-M10").status.startswith("done")


# ---------------------------------------------------------------- reports
def test_header_first_occurrence_wins(tmp_path):
    """merge.py fields(), 2026-11-19: a later 'verdict:' in the body overrode the header line."""
    r = tmp_path / "2026-11-20-pr-review-T-x-r1.md"
    r.write_text("verdict: approve\npublic_api: no\nbehaviour_change: no\nfails_without_fix: n/a\n\n"
                 "- earlier round said\nverdict: changes\n"
                 "outside: pymodaq_utils/config.py:GlobalConfig|docstring | GlobalConfig docstring says objects, returns dicts\n"
                 "summary: Adds six docstrings.\n")
    h = reports.header(r)
    assert h["verdict"] == "approve" and h["public_api"] == "no"
    assert reports.summary(r) == "Adds six docstrings."
    assert reports.outside(r) == [("pymodaq_utils/config.py:GlobalConfig|docstring",
                                   "GlobalConfig docstring says objects, returns dicts")]


def test_real_report():
    rs = reports.for_task("pymodaq_utils", "T-pymodaq_utils-M10")
    assert rs and reports.header(rs[-1])["verdict"] == "approve"


# ---- rework rule: two rounds, then only while the review converges
def _report(tmp_path, monkeypatch, rounds):
    from agentlib import reports
    d = tmp_path / "reports" / "pkg"
    d.mkdir(parents=True)
    for i, n in enumerate(rounds, 1):
        body = "".join(f"- a.py:{k} finding\n" for k in range(n)) or "None.\n"
        (d / f"2026-01-01-pr-review-T-1-r{i}.md").write_text(
            f"verdict: changes\npublic_api: no\nbehaviour_change: no\nfails_without_fix: n/a\n\n## Findings\n{body}\n"
            "## API\n- x:1 not a finding\n\nsummary: s\n")
    monkeypatch.setattr(reports, "AGENTS_DIR", tmp_path)
    return reports


@pytest.mark.parametrize("rounds,allowed", [([4], True), ([6, 5], True), ([6, 6], False), ([6, 3, 1], True),
                                            ([6, 3, 3], False), ([6, 5, 4, 3], False)])
def test_rework_rule(tmp_path, monkeypatch, rounds, allowed):
    reports = _report(tmp_path, monkeypatch, rounds)
    assert reports.rework_allowed("pkg", "T-1")[0] is allowed


def test_finding_count_reads_older_required_changes_reports(tmp_path):
    from agentlib import reports
    f = tmp_path / "x.md"
    f.write_text("verdict: changes\n\n## r1 findings\n- a:1 old\n\n## Required changes\n1. one\n2. two\n3. three\n\nsummary: s\n")
    assert reports.finding_count(f) == 3


def test_owner_granted_extra_round(tmp_path, monkeypatch):
    reports = _report(tmp_path, monkeypatch, [3, 3])
    assert reports.rework_allowed("pkg", "T-1")[0] is False
    assert reports.rework_allowed("pkg", "T-1", extra=1)[0] is True
    reports = _report(tmp_path / "b", monkeypatch, [3, 3, 3])
    assert reports.rework_allowed("pkg", "T-1", extra=1)[0] is False  # the grant is used up


def test_finding_count_accepts_text_after_the_findings_heading(tmp_path):
    from agentlib import reports
    f = tmp_path / "x.md"
    f.write_text("verdict: changes\n\n## r1 findings\n- a:1 old\n\n## Findings (what to change)\n- b:2 one\n- c:3 two\n\nsummary: s\n")
    assert reports.finding_count(f) == 2

from __future__ import annotations

from pellicule.kilo_tail import (
    collect_task_log_lines,
    parse_permission_line,
    reconcile_verdicts,
)
from pellicule.policy.models import PolicyEvaluation


def test_parse_permission_denied_line():
    parsed = parse_permission_line("permission denied: read sources/note.pdf")
    assert parsed.parsed is True
    assert parsed.verdict == "deny"
    assert parsed.tool == "read"
    assert parsed.path == "sources/note.pdf"


def test_reconcile_agree_on_matching_deny():
    evaluation = PolicyEvaluation(
        verdict="deny",
        ask_state=None,
        matched_rule="read: deny sources/**/*.pdf",
        rule_source="agents/plan.md",
        losers=[],
        tool="read",
        path="sources/note.pdf",
        motif="sources/note.pdf",
        dialect="v7",
        config_source="merged",
        agree=True,
        hypothesis=None,
        mcp_outside_table=False,
        builtin_rule=False,
    )
    parsed = parse_permission_line("permission denied: read sources/note.pdf")
    agree, hypothesis = reconcile_verdicts(evaluation, parsed, mode_confidence="exact")
    assert agree is True
    assert hypothesis is None


def test_reconcile_disagree_hypothesis_mode_unknown():
    evaluation = PolicyEvaluation(
        verdict="deny",
        ask_state=None,
        matched_rule="read: deny",
        rule_source="x",
        losers=[],
        tool="read",
        path="sources/note.pdf",
        motif="sources/note.pdf",
        dialect="v7",
        config_source="merged",
        agree=True,
        hypothesis=None,
        mcp_outside_table=False,
        builtin_rule=False,
    )
    parsed = parse_permission_line("permission denied: read other.pdf")
    agree, hypothesis = reconcile_verdicts(evaluation, parsed, mode_confidence="likely")
    assert agree is False
    assert hypothesis == "precedence"


def test_collect_task_log_lines_from_fixture(tmp_path):
    task_dir = tmp_path / "task-1"
    task_dir.mkdir()
    (task_dir / "api_conversation_history.json").write_text(
        '{"messages":[{"role":"tool","content":"permission denied: read sources/x.pdf"}]}',
        encoding="utf-8",
    )
    lines = collect_task_log_lines(task_dir)
    assert any("permission denied" in line for line in lines)

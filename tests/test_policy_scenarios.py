from __future__ import annotations

import pytest

from pellicule.policy.service import PolicyService


@pytest.mark.parametrize(
    ("mode", "tool", "arguments", "expected_verdict"),
    [
        ("planner", "read", {"path": "sources/a/b.pdf"}, "deny"),
        ("planner", "edit", {"path": "analysis/foo.py"}, "deny"),
        ("planner", "bash", {"command": 'python -c "print(1)"'}, "deny"),
        ("planner", "task", {"agent": "helper-b"}, "deny"),
        ("auditor", "edit", {"path": "NOTES.md"}, "deny"),
    ],
)
def test_five_denies_from_fixtures(
    lab_policy: PolicyService,
    mode: str,
    tool: str,
    arguments: dict,
    expected_verdict: str,
) -> None:
    result = lab_policy.evaluate(mode, tool, arguments)
    assert result.verdict == expected_verdict
    assert result.losers or result.matched_rule
    assert result.config_source == "merged"
    assert result.agree is True


def test_mcp_tool_outside_permission_table(lab_policy: PolicyService) -> None:
    result = lab_policy.evaluate("planner", "doc_sim_tool", {"path": "sources/a/b.pdf"})
    assert result.verdict == "allow"
    assert result.mcp_outside_table is True


def test_last_match_wins_has_losers(lab_policy: PolicyService) -> None:
    result = lab_policy.evaluate("planner", "read", {"path": "sources/x.pdf"})
    assert result.verdict == "deny"
    assert any("allow" in loser for loser in result.losers)


def test_agents_md_fallback_agree_false(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from pellicule.policy.loader import load_policy_config

    agents = Path(__file__).parent / "fixtures" / "lab" / "agents"
    monkeypatch.delenv("PELLICULE_MERGED_CONFIG", raising=False)
    monkeypatch.setenv("PELLICULE_MERGED_CONFIG", "")
    monkeypatch.delenv("KILO_CONFIG_CONTENT", raising=False)
    monkeypatch.setenv("PELLICULE_AGENTS_DIR", str(agents))
    monkeypatch.setattr("pellicule.policy.loader.merged_search_paths", lambda _workspace: [])
    cfg = load_policy_config()
    assert cfg.config_source == "agents_md"
    assert cfg.agree_without_log is False
    svc = PolicyService(cfg)
    ev = svc.evaluate("planner", "read", {"path": "sources/x.pdf"})
    assert ev.agree is False

from __future__ import annotations

from pellicule.mode_detect import (
    detect_mode,
    fingerprint_mode,
    slash_command_from_user_text,
)
from pellicule.policy.loader import load_policy_config
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parent / "fixtures" / "lab"


def test_fingerprint_planner_body(monkeypatch):
    monkeypatch.setenv("PELLICULE_MERGED_CONFIG", str(LAB_ROOT / "merged" / "kilo.jsonc"))
    monkeypatch.setenv("PELLICULE_AGENTS_DIR", str(LAB_ROOT / "agents"))
    cfg = load_policy_config()
    detection = fingerprint_mode("# Planner agent (fixture)", cfg.agent_bodies)
    assert detection.mode == "planner"
    assert detection.confidence == "likely"


def test_slash_command_from_config(monkeypatch):
    monkeypatch.setenv("PELLICULE_MERGED_CONFIG", str(LAB_ROOT / "merged" / "kilo.jsonc"))
    monkeypatch.setenv("PELLICULE_AGENTS_DIR", str(LAB_ROOT / "agents"))
    cfg = load_policy_config()
    cfg.slash_commands.add("ingestor")
    found = slash_command_from_user_text("/ingestor run", cfg.slash_commands)
    assert found.mode == "ingestor"
    assert found.confidence == "likely"


def test_detect_mode_exact_with_task_json(monkeypatch):
    monkeypatch.setenv("PELLICULE_MERGED_CONFIG", str(LAB_ROOT / "merged" / "kilo.jsonc"))
    monkeypatch.setenv("PELLICULE_AGENTS_DIR", str(LAB_ROOT / "agents"))
    cfg = load_policy_config()
    messages = [
        {"role": "system", "content": "# Planner agent (fixture)"},
        {"role": "user", "content": "hello"},
    ]
    detection = detect_mode(cfg, messages, task_mode="planner")
    assert detection.mode == "planner"
    assert detection.confidence == "exact"

from __future__ import annotations

from pathlib import Path

import pytest

from pellicule.policy import PolicyService, load_policy_config

LAB_ROOT = Path(__file__).resolve().parent / "fixtures" / "lab"


@pytest.fixture
def lab_policy(monkeypatch: pytest.MonkeyPatch) -> PolicyService:
    monkeypatch.setenv("PELLICULE_MERGED_CONFIG", str(LAB_ROOT / "merged" / "kilo.jsonc"))
    monkeypatch.setenv("PELLICULE_AGENTS_DIR", str(LAB_ROOT / "agents"))
    cfg = load_policy_config()
    return PolicyService(cfg)

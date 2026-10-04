from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import pellicule.settings as settings
from pellicule.settings import bootstrap_config, data_root, reset_bootstrap_for_tests


@pytest.fixture(autouse=True)
def _reset_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_bootstrap_for_tests()
    for name in (
        "PELLICULE_DATA",
        "PELLICULE_MERGED_CONFIG",
        "PELLICULE_PROXY_PORT",
        "PELLICULE_UI_PORT",
        "PELLICULE_CONFIG",
    ):
        monkeypatch.delenv(name, raising=False)


def test_toml_applies_when_env_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    toml = tmp_path / "pellicule.toml"
    toml.write_text(
        f'[data]\ndir = "{data_dir.as_posix()}"\n[server]\nproxy_port = 9999\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    bootstrap_config()
    assert data_root() == data_dir.resolve()
    assert settings.PROXY_PORT == 9999


def test_env_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = tmp_path / "from_env"
    other.mkdir()
    toml = tmp_path / "pellicule.toml"
    toml.write_text('[data]\ndir = "ignored"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PELLICULE_DATA", str(other))
    bootstrap_config()
    assert data_root() == other.resolve()


def test_cli_port_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    toml = tmp_path / "pellicule.toml"
    toml.write_text("[server]\nproxy_port = 8888\nui_port = 8889\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    bootstrap_config(proxy_port=7777, ui_port=7778)
    assert settings.PROXY_PORT == 7777
    assert settings.UI_PORT == 7778


def test_init_creates_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    from pellicule.init_cmd import run_init

    assert run_init(provider="lab", base_url="https://example/v1") == 0
    assert (tmp_path / "pellicule.toml").is_file()
    assert (tmp_path / "pellicule.keys").is_file()
    text = (tmp_path / "pellicule.keys").read_text(encoding="utf-8")
    assert "[lab]" in text
    assert "https://example/v1" in text


def test_init_skips_existing_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    from pellicule.init_cmd import run_init

    run_init()
    keys = tmp_path / "pellicule.keys"
    keys.write_text("unchanged", encoding="utf-8")
    run_init()
    assert keys.read_text(encoding="utf-8") == "unchanged"


def test_init_force_overwrites(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    from pellicule.init_cmd import run_init

    run_init()
    (tmp_path / "pellicule.keys").write_text("old", encoding="utf-8")
    run_init(force=True)
    assert "[default]" in (tmp_path / "pellicule.keys").read_text(encoding="utf-8")


def test_doctor_fails_without_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PELLICULE_DATA", str(tmp_path))
    bootstrap_config()
    from pellicule.doctor_cmd import run_doctor

    assert run_doctor() == 1


def test_doctor_ok_with_minimal_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PELLICULE_DATA", str(tmp_path))
    (tmp_path / "pellicule.keys").write_text(
        "[p]\nbase_url = https://x/v1\n",
        encoding="utf-8",
    )
    bootstrap_config()
    from pellicule.doctor_cmd import run_doctor

    assert run_doctor() == 0


def test_cli_doctor_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PELLICULE_DATA", str(tmp_path))
    (tmp_path / "pellicule.keys").write_text(
        "[p]\nbase_url = https://x/v1\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pellicule", "doctor"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert "fournisseur" in result.stdout.lower() or "OK" in result.stdout

from pathlib import Path

import pytest

from pellicule.keys import KeysError
from pellicule.upstream import resolve_model


def _write_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    monkeypatch.setenv("PELLICULE_DATA", str(tmp_path))
    (tmp_path / "pellicule.keys").write_text(body, encoding="utf-8")


def test_bare_model_uses_pellicule_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_keys(
        tmp_path,
        monkeypatch,
        "[albert]\nbase_url = https://albert.example/v1\napi_key = a\n"
        "[pellicule]\nbase_url = https://albert.example/v1\napi_key = p\n",
    )
    resolved = resolve_model("deepseek-v4-flash", None)
    assert resolved.credentials.name == "pellicule"
    assert resolved.credentials.api_key == "p"
    assert resolved.upstream_model == "deepseek-v4-flash"


def test_known_prefix_still_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_keys(
        tmp_path,
        monkeypatch,
        "[sidonie]\nbase_url = http://sidonie.example/v1\n"
        "[pellicule]\nbase_url = https://albert.example/v1\napi_key = p\n",
    )
    resolved = resolve_model("sidonie/qwen", None)
    assert resolved.credentials.name == "sidonie"
    assert resolved.upstream_model == "qwen"


def test_unknown_slash_id_is_not_rewritten(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_keys(
        tmp_path,
        monkeypatch,
        "[pellicule]\nbase_url = https://albert.example/v1\napi_key = p\n",
    )
    with pytest.raises(KeysError):
        resolve_model("org/deepseek-v4-flash", None)


def test_header_overrides_bare_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_keys(
        tmp_path,
        monkeypatch,
        "[sidonie]\nbase_url = http://sidonie.example/v1\n"
        "[pellicule]\nbase_url = https://albert.example/v1\napi_key = p\n",
    )
    resolved = resolve_model("deepseek-v4-flash", "sidonie")
    assert resolved.credentials.name == "sidonie"
    assert resolved.upstream_model == "deepseek-v4-flash"

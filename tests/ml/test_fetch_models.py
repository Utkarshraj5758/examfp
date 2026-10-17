"""The fetch script asks for exactly a pin's files at its commit. No network: the hub is faked."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from examfp.fairness.pins import NLI_PIN, NLI_PINS
from ml import fetch_models


def _fake_hub(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def hf_hub_download(**kwargs: object) -> str:
        calls.append(kwargs)
        target = Path(str(kwargs["local_dir"])) / str(kwargs["filename"])
        target.write_bytes(b"x")
        return str(target)

    hub = types.ModuleType("huggingface_hub")
    hub.hf_hub_download = hf_hub_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    return calls


@pytest.mark.parametrize("key", sorted(NLI_PINS))
def test_fetches_only_the_pinned_files_at_the_pinned_commit(
    key: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _fake_hub(monkeypatch)
    pin = NLI_PINS[key]
    target = fetch_models.fetch_nli(tmp_path, pin)
    assert target == tmp_path.joinpath(*pin.subdir.parts)
    assert [c["filename"] for c in calls] == list(pin.files)
    for call in calls:
        assert call["repo_id"] == pin.model_id
        assert call["revision"] == pin.revision
        assert call["local_dir"] == target


def test_cli_defaults_to_the_checkers_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    calls = _fake_hub(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["fetch_models", "--cache", str(tmp_path)])
    fetch_models.main()
    assert {c["repo_id"] for c in calls} == {NLI_PIN.model_id}
    assert NLI_PIN.version in capsys.readouterr().out


def test_cli_refuses_an_unpinned_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _fake_hub(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["fetch_models", "--model", "large", "--cache", str(tmp_path)])
    with pytest.raises(SystemExit):
        fetch_models.main()
    assert calls == []

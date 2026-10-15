"""Repo-hygiene guards (M4): packaging, task runner, CI, pre-commit and docs.

These pin down the contract in CLAUDE.md so it cannot silently drift: every
dependency exactly pinned, every subpackage shipped, the lint scope as written,
and the M4 artefacts present.
"""

from __future__ import annotations

import fnmatch
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT: dict[str, Any] = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
_PIN = re.compile(r"^[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_,\-]+\])?==[0-9][0-9A-Za-z.+!\-]*$")
_LINT_CONTRACT = "mypy --strict examfp service ml"


def _all_requirements() -> list[str]:
    project = PYPROJECT["project"]
    reqs: list[str] = list(project["dependencies"])
    for extra in project["optional-dependencies"].values():
        reqs.extend(extra)
    reqs.extend(PYPROJECT["build-system"]["requires"])
    return reqs


# --- packaging ----------------------------------------------------------------
def test_requires_python_is_311() -> None:
    assert PYPROJECT["project"]["requires-python"] == ">=3.11"


def test_extras_core_ml_service_dev_exist() -> None:
    extras = set(PYPROJECT["project"]["optional-dependencies"])
    assert {"core", "ml", "service", "dev"} <= extras


@pytest.mark.parametrize("requirement", _all_requirements())
def test_every_dependency_is_exactly_pinned(requirement: str) -> None:
    assert _PIN.match(requirement), f"{requirement!r} is not pinned with =="


def test_package_discovery_ships_every_subpackage() -> None:
    setuptools_cfg = PYPROJECT["tool"]["setuptools"]
    # An explicit `packages = [...]` list silently drops subpackages from wheels.
    assert "packages" not in setuptools_cfg or isinstance(setuptools_cfg["packages"], dict)
    include: list[str] = setuptools_cfg["packages"]["find"]["include"]

    def shipped(dotted: str) -> bool:
        return any(fnmatch.fnmatchcase(dotted, pattern) for pattern in include)

    for top in ("examfp", "ml", "service"):
        for init in (ROOT / top).rglob("__init__.py"):
            dotted = ".".join(init.parent.relative_to(ROOT).parts)
            assert shipped(dotted), f"{dotted} would be missing from the wheel"
    # Repo tooling must not be installed as generic top-level packages.
    for tooling in ("eval", "api", "tests"):
        assert not shipped(tooling)


# --- task runner --------------------------------------------------------------
TASKS = (ROOT / "tasks.ps1").read_text(encoding="utf-8")


@pytest.mark.parametrize("task", ["test", "lint", "demo", "bench", "train", "up", "smoke"])
def test_task_runner_defines(task: str) -> None:
    assert re.search(rf'^\s*"{task}"\s*\{{', TASKS, re.MULTILINE), f"task {task!r} missing"


def test_lint_task_uses_contract_scope() -> None:
    assert _LINT_CONTRACT in TASKS


def test_task_runner_is_ascii() -> None:
    # Windows PowerShell 5.1 reads BOM-less files as ANSI; keep the script ASCII.
    TASKS.encode("ascii")


# --- ignore rules, pre-commit, CI ----------------------------------------------
def test_gitignore_covers_generated_and_secret_artefacts() -> None:
    lines = {ln.strip() for ln in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    for entry in ("out/", "*.pdf", ".venv/", "eval/out/", "models/"):
        assert entry in lines, f".gitignore lacks {entry}"


def test_precommit_runs_ruff_and_strict_mypy() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "ruff check" in config
    assert _LINT_CONTRACT in config


def test_ci_runs_lint_and_tests_on_push_and_pr() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r"^\s+push:", ci, re.MULTILINE)
    assert re.search(r"^\s+pull_request:", ci, re.MULTILINE)
    assert 'python-version: "3.11"' in ci
    assert 'pip install -e ".[dev]"' in ci
    assert "tasks.ps1 lint" in ci and "tasks.ps1 test" in ci


# --- docs ----------------------------------------------------------------------
def test_notes_seeded_with_phase0_findings() -> None:
    notes = (ROOT / "NOTES.md").read_text(encoding="utf-8").lower()
    for finding in ("capacity", "channel durability", "mixed-radix"):
        assert finding in notes, f"NOTES.md lacks the {finding} finding"


def test_adr_records_two_modes() -> None:
    adr = (ROOT / "docs" / "ADR" / "0001-two-modes.md").read_text(encoding="utf-8")
    assert "Status" in adr
    assert "practical" in adr.lower() and "provable" in adr.lower()

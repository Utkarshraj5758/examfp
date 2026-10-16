"""Download the pinned NLI model into the local model cache (the only fetch).

``python -m ml.fetch_models [--cache models]`` downloads exactly the files in
:data:`examfp.fairness.pins.NLI_MODEL_FILES` at the pinned revision into
``<cache>/nli-deberta-v3-small/<revision>/``. The fairness checker then loads
those files with ``local_files_only=True``; nothing fetches at runtime
(CLAUDE.md, non-negotiable 8).
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from examfp.fairness.pins import (
    NLI_MODEL_FILES,
    NLI_MODEL_ID,
    NLI_MODEL_REVISION,
    nli_model_subdir,
)

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "models"


def fetch_nli(cache: Path) -> Path:
    """Download the pinned NLI files into ``cache``; return the model directory.

    Guarantees: fetches only the pinned files at the pinned commit (never a
    branch name), so a re-run cannot pick up a newer upload.
    """
    from huggingface_hub import hf_hub_download

    target = cache / Path(*nli_model_subdir().parts)
    target.mkdir(parents=True, exist_ok=True)
    for name in NLI_MODEL_FILES:
        hf_hub_download(
            repo_id=NLI_MODEL_ID,
            filename=name,
            revision=NLI_MODEL_REVISION,
            local_dir=target,
        )
    return target


def sha256(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    target = fetch_nli(args.cache)
    print(f"{NLI_MODEL_ID}@{NLI_MODEL_REVISION} -> {target}")
    for name in NLI_MODEL_FILES:
        print(f"  {name:<24} sha256 {sha256(target / name)}")


if __name__ == "__main__":
    main()

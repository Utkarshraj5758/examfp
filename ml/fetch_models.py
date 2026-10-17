"""Download a pinned NLI model into the local model cache (the only fetch).

``python -m ml.fetch_models [--model small] [--cache models]`` downloads exactly
the files of :data:`examfp.fairness.pins.NLI_PINS` ``[model]`` at its pinned
revision into ``<cache>/<repository name>/<revision>/``. The default is the
checker's model, :data:`examfp.fairness.pins.NLI_PIN`. The fairness checker then
loads those files with ``local_files_only=True``; nothing fetches at runtime
(CLAUDE.md, non-negotiable 8).
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from examfp.fairness.pins import NLI_PIN, NLI_PINS, NliPin, nli_pin

DEFAULT_CACHE = Path(__file__).resolve().parents[1] / "models"


def fetch_nli(cache: Path, pin: NliPin = NLI_PIN) -> Path:
    """Download ``pin``'s files into ``cache``; return the model directory.

    Guarantees: fetches only the pinned files at the pinned commit (never a
    branch name), so a re-run cannot pick up a newer upload.
    """
    from huggingface_hub import hf_hub_download

    target = cache / Path(*pin.subdir.parts)
    target.mkdir(parents=True, exist_ok=True)
    for name in pin.files:
        hf_hub_download(
            repo_id=pin.model_id,
            filename=name,
            revision=pin.revision,
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
    parser.add_argument("--model", choices=sorted(NLI_PINS), default=NLI_PIN.key,
                        help=f"which pinned model to fetch (default: {NLI_PIN.key})")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    pin = nli_pin(args.model)
    target = fetch_nli(args.cache, pin)
    print(f"{pin.version} -> {target}")
    for name in pin.files:
        print(f"  {name:<24} sha256 {sha256(target / name)}")


if __name__ == "__main__":
    main()

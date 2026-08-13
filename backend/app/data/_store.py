"""Loader for the generated reference datasets.

The files under ``app/data/generated`` are produced by
``scripts/build_reference_data.py`` and committed, so the app has full global
coverage with no network access and no database seeding at startup.
"""

from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

GENERATED_DIR = Path(__file__).parent / "generated"


class ReferenceDataMissing(RuntimeError):
    """The generated dataset is absent -- the build script has not been run."""


@lru_cache(maxsize=8)
def load(name: str) -> Any:
    """Read and parse ``generated/<name>.json.gz``, cached for the process."""
    path = GENERATED_DIR / f"{name}.json.gz"
    if not path.is_file():
        raise ReferenceDataMissing(
            f"Missing reference dataset '{path.name}'. Generate it with:\n"
            f"    python scripts/build_reference_data.py"
        )
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)

""".env loading with a pure-stdlib parser (ADR-0002: zero third-party runtime deps).

Semantics mirror the reference project's ``config/env.py``: candidates are
loaded in order, and only the last candidate may override variables that are
already present in the real environment.
"""

from __future__ import annotations

import os
from pathlib import Path

from paths import PROJECT_ROOT

ENV_FILE_VAR = "QUANT_SANDBOX_ENV"


def env_file_candidates() -> list[Path]:
    """Candidate .env paths in load order; the last entry wins."""
    candidates: list[Path] = []
    explicit = os.environ.get(ENV_FILE_VAR, "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(PROJECT_ROOT / ".env")
    return candidates


def _parse_env_file(path: Path, *, override: bool) -> None:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value


def load_env(candidates: list[Path] | None = None) -> list[str]:
    """Load .env candidates into ``os.environ``; return the paths actually loaded.

    Real environment variables win over every candidate except the last one
    (local ``.env``), which mirrors the reference project's override rule.
    """
    if candidates is None:
        candidates = env_file_candidates()
    loaded: list[str] = []
    for index, path in enumerate(candidates):
        if not path.is_file():
            continue
        _parse_env_file(path, override=index == len(candidates) - 1)
        loaded.append(str(path))
    return loaded

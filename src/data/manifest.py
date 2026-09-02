"""Dataset manifest contract: one sha256 per data file, next to the data (ADR-0004).

Every dataset directory carries a ``manifest.json`` recording ``source``,
``generated_at`` and one sha256 per covered file. This is this project's
fixed data-engineering format; the frozen investment-gate dataset (lesson 19)
reuses it. Problem reports are user-visible copy and therefore Chinese
(ADR-0005); an empty problem list means every digest matched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

MANIFEST_NAME = "manifest.json"
_CHUNK = 1 << 16


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(source: str, generated_at: str, files: Mapping[str, Path]) -> dict:
    """Digest ``files`` (name → path) into the fixed manifest shape."""
    return {
        "source": source,
        "generated_at": generated_at,
        "files": {name: sha256_file(path) for name, path in sorted(files.items())},
    }


def write_manifest(directory: Path, manifest: dict) -> Path:
    path = directory / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def verify_manifest(directory: Path) -> list[str]:
    """Recompute every listed digest; return one Chinese problem per divergence."""
    path = directory / MANIFEST_NAME
    if not path.is_file():
        return [f"{MANIFEST_NAME} 缺失(数据目录:{directory})"]
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"{MANIFEST_NAME} 不是合法 JSON:{error}"]
    files = manifest.get("files")
    if not isinstance(files, dict):
        return [f"{MANIFEST_NAME} 缺少 files 表:{path}"]
    problems = []
    for name, recorded in files.items():
        data_path = directory / name
        if not data_path.is_file():
            problems.append(f"被 manifest 记录的文件缺失:{name}")
        elif sha256_file(data_path) != recorded:
            problems.append(f"sha256 不一致(文件在入库后被改动?):{name}")
    return problems

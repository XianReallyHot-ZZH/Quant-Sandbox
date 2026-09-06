"""数据集 manifest 契约:每个数据文件配一个 sha256,与数据放在一起(ADR-0004)。

每个数据集目录都带一份 ``manifest.json``,记录 ``source``、
``generated_at`` 和每个被覆盖文件的一个 sha256 指纹。这是本项目数据
工程的固定格式;课 19 的冻结投资门数据集复用同一格式。问题报告属于
用户可见文案,因此用中文(ADR-0005);空问题列表 = 所有指纹全部对上。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

MANIFEST_NAME = "manifest.json"
# 每次读 64KiB(1<<16 字节)算哈希——文件再大也不整份读进内存。
_CHUNK = 1 << 16


def sha256_file(path: Path) -> str:
    """算一个文件的 sha256,返回 64 位十六进制文本。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        # iter(函数, 哨兵):反复调用函数,直到它返回哨兵值 b""
        # (文件读尽)为止——惰性分块读取的惯用法。
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(source: str, generated_at: str, files: Mapping[str, Path]) -> dict:
    """把 ``files``(名字 → 路径)算成固定形状的 manifest(dict)。

    sorted 保证键序稳定——同一批文件无论何时算,manifest 字节都一致。
    """
    return {
        "source": source,
        "generated_at": generated_at,
        "files": {name: sha256_file(path) for name, path in sorted(files.items())},
    }


def write_manifest(directory: Path, manifest: dict) -> Path:
    """把 manifest 写成 UTF-8 的 JSON 文件(缩进 2;ensure_ascii=False
    让中文原样落盘而不是 \\u 转义)。返回写出的路径。"""
    path = directory / MANIFEST_NAME
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def verify_manifest(directory: Path) -> list[str]:
    """重算每个登记文件的指纹;每处不一致返回一条中文问题描述。"""
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
            # 任何篡改都要以「点名的问题」浮出水面,不许沉默(ADR-0006 哲学)。
            problems.append(f"sha256 不一致(文件在入库后被改动?):{name}")
    return problems

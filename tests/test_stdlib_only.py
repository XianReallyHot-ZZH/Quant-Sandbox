"""ADR-0002 contract: product code imports the stdlib only (pytest is the sole dev dep).

First-party top-level names (modules and packages under src/) are allowed
automatically; every other import must appear in ``sys.stdlib_module_names``.
This test is a regression lock: green on landing, and it keeps future lessons
from quietly adding third-party runtime dependencies.

Known limitation: a third-party package physically vendored into src/ would be
whitelisted by name too — that is a deliberate act no AST guard should have to
catch; code review is the control for it.
"""

import ast
import sys

from paths import PROJECT_ROOT

PRODUCT_FILES = sorted((PROJECT_ROOT / "src").rglob("*.py")) + [
    PROJECT_ROOT / "app.py",
    PROJECT_ROOT / "verify.py",
]


def _imported_roots(path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _first_party_top_level() -> set[str]:
    src = PROJECT_ROOT / "src"
    return {entry.stem for entry in src.iterdir() if entry.suffix == ".py"} | {
        entry.name for entry in src.iterdir() if entry.is_dir()
    }


def test_product_code_imports_only_stdlib() -> None:
    allowed = set(sys.stdlib_module_names) | _first_party_top_level()
    offenders: dict[str, list[str]] = {}
    for product_file in PRODUCT_FILES:
        for module_root in _imported_roots(product_file) - allowed:
            offenders.setdefault(module_root, []).append(product_file.name)
    assert offenders == {}, f"产品代码出现非标准库 import:{offenders}"

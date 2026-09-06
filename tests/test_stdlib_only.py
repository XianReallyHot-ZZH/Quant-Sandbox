"""ADR-0002 契约:产品代码只 import 标准库(pytest 是唯一 dev 依赖)。

src/ 下的首方顶层名(模块与包)自动放行;其余每个 import 都必须出现在
``sys.stdlib_module_names``(Python 自带的标准库名单)里。本测试是回归
锁:落地即绿,守住「后续课程不许悄悄引入第三方运行时依赖」。

已知局限:把第三方包物理拷进 src/ 也会被按名放行——那是刻意行为,
AST 守卫不必抓它;那一层由代码评审把关。
"""

import ast
import sys

from paths import PROJECT_ROOT

# rglob("*.py") 递归收齐 src 下全部源文件,再加上两个入口脚本。
PRODUCT_FILES = sorted((PROJECT_ROOT / "src").rglob("*.py")) + [
    PROJECT_ROOT / "app.py",
    PROJECT_ROOT / "verify.py",
]


def _imported_roots(path) -> set[str]:
    # ast.parse 把源码解析成语法树;ast.walk 深度优先走遍每个节点,
    # 捡出所有 import 语句,取每个名字的顶层部分(如 a.b.c → a)。
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # import a, b.c → {"a", "b"}
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # from a.b import x → {"a"};level==0 排除相对导入(from . import x)。
            roots.add(node.module.split(".")[0])
    return roots


def _first_party_top_level() -> set[str]:
    # 首方名 = src 下直接子模块的文件名(去后缀)+ 子目录(包)名。
    src = PROJECT_ROOT / "src"
    return {entry.stem for entry in src.iterdir() if entry.suffix == ".py"} | {
        entry.name for entry in src.iterdir() if entry.is_dir()
    }


def test_product_code_imports_only_stdlib() -> None:
    # 白名单 = 标准库名单 ∪ 首方顶层名;每个产品文件的 import 根减去
    # 白名单,剩下的就是违例者,按「依赖名 → 文件名列表」归组报出。
    allowed = set(sys.stdlib_module_names) | _first_party_top_level()
    offenders: dict[str, list[str]] = {}
    for product_file in PRODUCT_FILES:
        for module_root in _imported_roots(product_file) - allowed:
            offenders.setdefault(module_root, []).append(product_file.name)
    assert offenders == {}, f"产品代码出现非标准库 import:{offenders}"

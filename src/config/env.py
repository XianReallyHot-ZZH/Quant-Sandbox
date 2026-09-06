""".env 加载:纯标准库手写解析器(ADR-0002:零第三方运行时依赖)。

参照物用 python-dotenv 读 .env,另带一个 try/except 的手写后备;我们
按零依赖约定直接手写。加载语义逐条镜像参照物的 ``config/env.py``
(研报 §3.3):候选文件按顺序加载,但**只有最后一个候选**(本地
``.env``)允许覆盖真实环境里已存在的变量——即开发者本机的 local .env
是最强候选,连 shell 导出都能压过。
"""

from __future__ import annotations

import os
from pathlib import Path

from paths import PROJECT_ROOT

# 这个环境变量本身用来指定 .env 文件的位置(把配置指到别处的能力)。
ENV_FILE_VAR = "QUANT_SANDBOX_ENV"


def env_file_candidates() -> list[Path]:
    """按加载顺序返回候选 .env 路径;最后一项优先级最高(可覆盖一切)。"""
    candidates: list[Path] = []
    # 若设置了 QUANT_SANDBOX_ENV,显式指定的文件排最前(非末位,只能补缺)。
    explicit = os.environ.get(ENV_FILE_VAR, "").strip()
    if explicit:
        candidates.append(Path(explicit))
    # 仓库根的 .env 永远是最后一个候选 = 最强候选(参照物「local override wins」)。
    candidates.append(PROJECT_ROOT / ".env")
    return candidates


def _parse_env_file(path: Path, *, override: bool) -> None:
    # 逐行解析一个 .env 文件,把 key=value 写进 os.environ。
    # override=False 时只补缺(变量已存在则跳过);True 时强行覆盖。
    # 名字前的下划线表示「模块内部使用」,别的模块不应 import 它。
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        # 空行、# 注释行、没有 = 的行直接跳过。
        if not line or line.startswith("#") or "=" not in line:
            continue
        # 只按第一个 = 切一刀:value 里再出现 = 也属于值(如 token=abc=def)。
        key, value = line.split("=", 1)
        key = key.strip()
        # 去掉值两侧的引号:先去双引号再去单引号,覆盖 "x" 与 'x' 两种写法。
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        if override or key not in os.environ:
            os.environ[key] = value


def load_env(candidates: list[Path] | None = None) -> list[str]:
    """把候选 .env 依次装入 ``os.environ``;返回真正被加载的路径列表。

    真实环境变量赢过除最后一个候选(本地 ``.env``)之外的一切——这是
    参照物的覆盖规则,本课程如实继承(含其怪癖,见模块 docstring)。
    """
    if candidates is None:
        candidates = env_file_candidates()
    loaded: list[str] = []
    # enumerate 给循环配上从 0 开始的下标;只有遍历到最后一项时才 override=True。
    for index, path in enumerate(candidates):
        if not path.is_file():
            continue
        _parse_env_file(path, override=index == len(candidates) - 1)
        loaded.append(str(path))
    return loaded

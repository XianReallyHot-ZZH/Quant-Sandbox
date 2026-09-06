"""布局常量:仓库根目录即产品根目录(CONTEXT.md「仓库布局」行)。

`app.py`、`src/`、`tests/` 都直接放在仓库根下,所以「产品从哪个目录起、
数据放在哪里」只需要三个常量说清楚。后续所有课程统一从本模块 import,
禁止各自手拼相对路径——路径只有一个事实源。
"""

from __future__ import annotations
# ↑ 作用:让类型标注变成「延迟求值」的字符串,可以随便写向前引用。
#   Python 3.11 下多数写法其实可以省掉它,保留是为了全仓库风格统一。

from pathlib import Path

# __file__ 是「本源码文件自己的路径」;resolve() 把它变成绝对路径
# (消掉 ..、符号链接);parents[1] 取上两级目录:本文件在
# <仓库根>/src/paths.py,parents[0] 是 src/,parents[1] 是仓库根。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"

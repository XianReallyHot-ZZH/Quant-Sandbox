"""测试引导:让仓库根的入口脚本(app.py、verify.py)可以被 import。

pytest 会自动把本文件当「共享夹具/引导文件」:它先于所有测试被加载,
这里做的事——把仓库根插进 sys.path——对每个测试文件生效。
"""

import sys

from paths import PROJECT_ROOT

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

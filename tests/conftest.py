"""Test bootstrap: make repo-root entry points (app.py, verify.py) importable."""

import sys

from paths import PROJECT_ROOT

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

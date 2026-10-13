"""Expose the directory next to the frozen executable to runtime code."""

import os
import sys
from pathlib import Path


if getattr(sys, "frozen", False):
    os.environ.setdefault("REPORT_ENGINE_RUNTIME_DIR", str(Path(sys.executable).resolve().parent / "runtime"))

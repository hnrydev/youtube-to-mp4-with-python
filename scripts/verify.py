"""Pre-deploy checks: compile Python, import app modules (run from repo root)."""

from __future__ import annotations

import os
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _py_compile(*rel: str) -> None:
    for p in rel:
        path = os.path.join(_ROOT, p)
        subprocess.check_call([sys.executable, "-m", "py_compile", path], cwd=_ROOT)


def _import_core_and_server() -> None:
    os.chdir(_ROOT)
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    import resolve_core  # noqa: F401
    import server  # noqa: F401


def main() -> None:
    _py_compile("resolve_core.py", "server.py", os.path.join("api", "resolve.py"))
    _import_core_and_server()
    print("verify: ok")


if __name__ == "__main__":
    main()

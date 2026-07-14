"""Launch the studio: python3 -m poolmine.ui [--port 8803]"""

from __future__ import annotations

import argparse
from pathlib import Path

from poolmine import workspace
from poolmine.index import DEFAULT_INDEX_PATH
from poolmine.ui.server import serve


def main() -> None:
    ap = argparse.ArgumentParser(prog="poolmine.ui")
    ap.add_argument("--project", metavar="DIR", help="Project workspace (default: cwd or $POOLMINE_HOME).")
    ap.add_argument("--index", default=None, help="Path to database.json.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8803)
    a = ap.parse_args()

    explicit_index = a.index is not None
    if explicit_index:
        a.index = str(Path(a.index).expanduser().resolve())
    workspace.enter(workspace.resolve_root(a.project))
    index_path = Path(a.index) if explicit_index else DEFAULT_INDEX_PATH
    serve(a.host, a.port, index_path)


if __name__ == "__main__":
    main()

"""Project workspaces.

Each poolmine project keeps its data under a project root: ``<root>/database``
(the index) and ``<root>/output`` (clips); downloaded videos live under
``<root>/new_library`` (here a symlink to the 4 TB drive). The root defaults to
the current directory; ``--project DIR`` or the ``POOLMINE_HOME`` env var select
a different one.

Because the index stores paths relative to the root, entering a workspace simply
means ``chdir`` into it — then every existing relative path resolves correctly
(including ``new_library/<id>.mp4`` via the symlink). Resolve any user-supplied
paths to absolute *before* calling :func:`enter`.
"""

from __future__ import annotations

import os
from pathlib import Path


def resolve_root(cli_value: str | None = None) -> Path:
    raw = cli_value or os.environ.get("POOLMINE_HOME")
    return Path(raw).expanduser().resolve() if raw else Path.cwd()


def enter(root: Path) -> Path:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    os.chdir(root)
    return root

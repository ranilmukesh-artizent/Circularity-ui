"""Read the B1 golden files (fixtures/golden, written by apps/web/scripts/dump-golden.mjs).

The dump writes an object that appears twice only once and replaces later occurrences with {"$ref": "<path>"},
where <path> is a JSONPath-like location from the file's root ("$.routes[0]", "$[3].recommendation").
`load()` returns the data with every reference replaced by the object it points to.
"""

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from sim.config import get_settings

_TOKEN = re.compile(r"\.([^.\[\]]+)|\[(\d+)\]")


def golden_dir() -> Path:
    return Path(get_settings().golden_dir)


def _walk(root: Any, path: str) -> Any:
    if not path.startswith("$"):
        raise ValueError(f"bad $ref path {path!r}")
    node = root
    for key, index in _TOKEN.findall(path[1:]):
        node = node[int(index)] if index else node[key]
    return node


def _resolve(node: Any, root: Any) -> Any:
    if isinstance(node, dict):
        if set(node) == {"$ref"}:
            return _resolve(_walk(root, node["$ref"]), root)
        return {k: _resolve(v, root) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve(v, root) for v in node]
    return node


@cache
def load(name: str) -> Any:
    """Load fixtures/golden/<name>.json with back-references resolved. Cached: treat the result as read-only."""
    path = golden_dir() / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `npm run golden` in apps/web (docs/backend-steps.md, B1)")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _resolve(raw, raw)

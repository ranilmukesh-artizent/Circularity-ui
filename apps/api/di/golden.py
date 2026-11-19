"""Read the B1 golden files (fixtures/golden). Repeated objects are written once and referenced as {"$ref": "<path>"};
`load()` resolves those references."""

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from di.config import get_settings

_TOKEN = re.compile(r"\.([^.\[\]]+)|\[(\d+)\]")


def _walk(root: Any, path: str) -> Any:
    node = root
    for key, idx in _TOKEN.findall(path[1:]):
        node = node[int(idx)] if idx else node[key]
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
    """fixtures/golden/<name>.json with references resolved. Cached: treat as read-only."""
    raw = json.loads((Path(get_settings().golden_dir) / f"{name}.json").read_text(encoding="utf-8"))
    return _resolve(raw, raw)

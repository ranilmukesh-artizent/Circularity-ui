"""Small XML helpers shared by the DMN and BPMN exports (plan 9, P9-8.21).

Owns: `ncname` (a safe XML id), `sub` (add a child with text and attributes) and `serialize` (an element tree to a UTF-8
text with its XML declaration, indented). The default namespace is written as an `xmlns` attribute on the root, so
nothing touches ElementTree's global namespace registry.
Never does: know a DMN or BPMN element; read a flow, a pack or the database.
"""

import re
import xml.etree.ElementTree as ET
from typing import Any

_BAD = re.compile(r"[^A-Za-z0-9_.-]+")


def ncname(*parts: object) -> str:
    """An XML id (an NCName) from the parts: other characters become `_`, and it starts with a letter or `_`."""
    s = _BAD.sub("_", "_".join(str(p) for p in parts)).strip("_") or "x"
    return s if s[0].isalpha() else "_" + s


def sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: Any) -> ET.Element:
    """A child of `parent`: its text, and the attributes that are not None."""
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items() if v is not None})
    if text is not None:
        el.text = text
    return el


def serialize(root: ET.Element) -> str:
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"

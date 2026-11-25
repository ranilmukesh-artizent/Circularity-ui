"""Static checks of a connector spec before anyone connects from it (plan 9, P9-8.6; registry entry I-18).

    check_spec(spec, host) -> list[SpecError(field, message)]

A spec is the connection fields of a registry entry: `resources`, `paging`, `auth_kind`, `auth_params` (the keys
di.connectors.configured reads). The checks are pure and need no network:
- every absolute URL in it has the connection's host (a spec never sends a call, or a token, to another host);
- a resource is read with GET or HEAD only;
- paging ends: a next key, a next link or cursor path, or a total; `single_page` always ends;
- no field named like a secret holds a value (`SECRET_WORDS`, di.core.redact): a credential goes to the encrypted
  store, and the message names the field, never the value;
- every resource names its `data_selector` and `id_field`.
The `import` key (the importer's notes) is not part of the connection fields and is skipped.

Owns: the list of problems. Never does: fetch, repair or save a spec, or echo a value found in it.
"""
# ruff: noqa: E501 - long lines in the messages

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from di.connectors.configured import PAGING_TYPES
from di.core.redact import SECRET_WORDS

READ_METHODS = ("GET", "HEAD")
META_KEY = "import"  # the importer's notes, kept beside the connection fields
_NOT_SECRETS = ("token_path",)  # a URL path to the token endpoint, not a credential
_ABSOLUTE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:)?//")


@dataclass(frozen=True)
class SpecError:
    field: str
    message: str


def check_spec(spec: Mapping[str, Any], host: str) -> list[SpecError]:
    errors: list[SpecError] = []
    _walk({k: v for k, v in spec.items() if k != META_KEY}, "", host.lower(), errors)
    resources = spec.get("resources") or []
    for i, r in enumerate(resources if isinstance(resources, list) else []):
        _resource(r if isinstance(r, Mapping) else {}, f"resources[{i}]", errors)
    if resources:
        _paging(spec.get("paging"), errors)
    return errors


def _walk(value: Any, field: str, host: str, errors: list[SpecError]) -> None:
    if isinstance(value, Mapping):
        for k, v in value.items():
            here = f"{field}.{k}" if field else str(k)
            low = str(k).lower()
            if v not in (None, "", [], {}) and low not in _NOT_SECRETS and any(w in low for w in SECRET_WORDS):
                errors.append(
                    SpecError(
                        here, f"{here} holds a value. A credential is entered when the connection is made, never in the spec."
                    )
                )
            _walk(v, here, host, errors)
    elif isinstance(value, list):
        for n, v in enumerate(value):
            _walk(v, f"{field}[{n}]", host, errors)
    elif isinstance(value, str) and _ABSOLUTE.match(value):
        other = (urlparse(value).hostname or "").lower()
        if other != host:
            errors.append(
                SpecError(field, f"{field} calls {other or 'another host'}, not the connection's host {host or '(none)'}.")
            )


def _resource(r: Mapping[str, Any], field: str, errors: list[SpecError]) -> None:
    if not str(r.get("path") or "").strip():
        errors.append(SpecError(f"{field}.path", "The resource has no path."))
    method = str(r.get("method") or "GET").upper()
    if method not in READ_METHODS:
        errors.append(SpecError(f"{field}.method", f"A resource is read with GET or HEAD, not {method}."))
    if not str(r.get("data_selector") or "").strip():
        errors.append(SpecError(f"{field}.data_selector", "Say where the records are in the response (data_selector)."))
    if not str(r.get("id_field") or "").strip():
        errors.append(SpecError(f"{field}.id_field", "Say which field is the record's id (id_field)."))


def _paging(paging: Any, errors: list[SpecError]) -> None:
    p = paging if isinstance(paging, Mapping) else {}
    kind = str(p.get("type") or p.get("style") or "")
    if kind not in PAGING_TYPES:
        errors.append(SpecError("paging", f"Paging is one of {', '.join(PAGING_TYPES)}."))
        return
    ends = {
        "single_page": True,
        "header_link": True,  # the Link header has no rel="next" on the last page
        "json_link": bool(p.get("next_url_path") or p.get("next_key")),
        "cursor": bool(p.get("cursor_path") or p.get("next_key")),
        "header_cursor": bool(p.get("cursor_path")),
        "offset": bool(p.get("next_key") or p.get("total_key")),
        "page_number": bool(p.get("next_key") or p.get("total_key")),
    }[kind]
    if not ends:
        errors.append(SpecError("paging", f"Paging {kind} has no next key, next link, cursor path or total to say when it ends."))

"""The registry of LLM playbook versions (plan 9, P9-2.2; used with registry entry I-8).

    register(name, version, build)   a playbook version: `build()` makes its `LoopSpec` when asked
    spec_for(name, version)          that version's spec, or None when it is not registered (any more)
    latest(name)                     the version a new run starts on (the last one registered), or None
    known(name)                      is `name` an LLM playbook

A run stores the version it started on (`agent_run.state.playbook_version`) and resumes on that version only: a
version that is gone ends the run (`runtime`). Versions are plain strings, compared by equality, never ordered.
Never does: run a loop or read the database.
"""

from collections.abc import Callable

from di.services.agents.loop import LoopSpec

_VERSIONS: dict[str, dict[str, Callable[[], LoopSpec]]] = {}


def register(name: str, version: str, build: Callable[[], LoopSpec]) -> None:
    """Add (or replace) a version; it becomes the latest."""
    versions = _VERSIONS.setdefault(name, {})
    versions.pop(version, None)  # re-registering moves it to the end
    versions[version] = build


def unregister(name: str, version: str) -> None:
    versions = _VERSIONS.get(name, {})
    versions.pop(version, None)
    if not versions:
        _VERSIONS.pop(name, None)


def spec_for(name: str, version: str) -> LoopSpec | None:
    build = _VERSIONS.get(name, {}).get(version)
    return build() if build else None


def latest(name: str) -> str | None:
    versions = _VERSIONS.get(name)
    return next(reversed(versions)) if versions else None


def known(name: str) -> bool:
    return name in _VERSIONS

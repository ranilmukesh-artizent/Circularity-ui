"""Typed inputs and outputs of the eval tasks (plan 9, P9-2.15). Plain data: no evaluator or task logic here.

Owns: what each dataset's `Case.inputs` and a task's output look like. Never does: touch the database or a model.
"""

from dataclasses import dataclass, field
from typing import Any

HELD_LIKE = frozenset({"held", "waiting", "exception"})  # a stage status that means a person must look


@dataclass(frozen=True)
class ChainIn:
    """A chain scenario: an existing case, or a case opened from data (`template` and its `facts`)."""

    case_id: str | None = None
    template: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChainOut:
    case_id: str
    run_status: str
    route: str | None  # the case's recommendation after the run (the decision rules', never a model's)
    stages: dict[str, str]  # stage id -> record status
    hold_reasons: list[str]  # every reason a stage record carries, sorted, deduplicated
    journal: list[str]  # the actions the run's writes put in the journal
    proposals: list[str]  # the actions held for a person
    readings: list[str] = field(default_factory=list)  # the texts of every model reading on the stage records
    facts_blob: str = ""  # the case and stage outputs as JSON: the numbers a reading may use


@dataclass(frozen=True)
class ConfigIn:
    """A configuration-agent scenario: a description, the packs it is read against, and an answer to the question."""

    text: str
    packs: tuple[str, ...] = ("tool_fleet", "device")
    guard: str | None = (
        None  # "recall": tool fleet with a recall check and a locked repair guardrail; "blacklist": device with a blacklist check
    )
    answer: str | None = "skip"
    hostile: bool = False  # a model that obeys the planted text drafts first; the checks still win


@dataclass
class ConfigOut:
    pack: str
    nearest_only: bool
    question: bool
    ops: list[tuple[str, str]]  # (op, target)
    blocked: list[str]  # the guardrail each blocked item names
    by_model: bool
    dropped_guardrail: bool  # a skip got through, or a tighten moved a locked guardrail the wrong way


@dataclass(frozen=True)
class InjectionIn:
    surface: str
    plant: str  # which of the three planted instructions
    text: str
    goal: str  # approve | publish | drop_guardrail


@dataclass
class InjectionOut:
    surface: str
    goal: str
    journal: list[str]
    allowed: list[str]  # the actions the same scenario's journal holds with no model and no planted text
    proposals: list[str]
    stages: dict[str, str]
    baseline_stages: dict[str, str]
    readings: list[str]
    facts_blob: str
    config: ConfigOut | None = None  # the configuration-description surface


@dataclass
class ModelFirstIn:
    name: str  # the path: stage_reading_invented_number, stage_reading_unranked_route, exception_owner, workflow_publish
    hostile: bool = True


@dataclass
class ModelFirstOut:
    """One model-first path on a scripted model: what code kept of what the model wrote."""

    kept: dict[str, Any]
    journal: list[str] = field(default_factory=list)

"""The case process as BPMN 2.0 XML (plan 9, P9-8.21; enabler E 8.2 "BPMN 2.0 export of the case process"). Pure.

Owns: `ProcessDef` (what the process needs: triggers, stage SLAs, approvals), `process_of` (it from a pack and a flow) and
`to_bpmn`. The process runs: a start event per trigger, a service task per stage of I-1 (receive, match, condition,
value), a business rule task that refers to the DMN decision (`camunda:decisionRef`, the attribute Camunda reads), the
stage "decide", a user task per approval guardrail, an exclusive gateway that splits to the routes and one that joins them,
the service tasks "execute" and "close", and one end event. A stage with an SLA has a non-interrupting timer boundary event
(ISO 8601 duration); when it fires the platform escalates the item (di.services.cases.process.on_sla), which BPMN only notes.
Never does: draw a diagram (no BPMNDI: a tool lays it out), validate against an XSD, read the database, or carry what BPMN
has no form for (locked stages, scopes, shadow runs; the process documentation says so).
Decision: the pack gives SLAs per kind of item (`runtime.sla_hours`), not per stage; each stage takes the `exception` SLA,
because an exception raised in a stage is due within it.
"""

import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import pairwise

from di.services.modeler.export_xml import ncname, serialize, sub
from di.services.modeler.flow import Flow
from di.services.modeler.pack import Pack
from di.services.modeler.stages import STAGE_KEYS, StageKey

BpmnNs = "http://www.omg.org/spec/BPMN/20100524/MODEL"
CAMUNDA = "http://camunda.org/schema/1.0/bpmn"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
LOSSY = "Exported from the Modeler. Locked stages, scopes and shadow runs have no BPMN form."


@dataclass(frozen=True)
class ProcessDef:
    key: str
    name: str
    triggers: tuple[str, ...]  # one start event each
    stage_sla_hours: Mapping[StageKey, float]  # a timer boundary event per stage listed
    approvals: tuple[tuple[str, str, str], ...]  # (guardrail id, owner role, text): a user task each


def process_of(pack: Pack, flow: Flow) -> ProcessDef:
    triggers = tuple(n["label"] for n in flow["nodes"] if n["t"] == "trigger") or ("Asset returned",)
    sla = pack.runtime.sla_hours.get("exception")
    return ProcessDef(
        pack.key, pack.name, triggers, {k: sla for k in STAGE_KEYS} if sla else {},
        tuple((g.id, g.owner, g.text) for g in pack.guardrails if g.type == "Approval"),
    )  # fmt: skip


def _duration(hours: float) -> str:
    return f"PT{hours:g}H"


class _Builder:
    def __init__(self, p: ET.Element) -> None:
        self.p = p
        self.n = 0

    def flow(self, a: str, b: str, name: str | None = None, cond: str | None = None) -> None:
        self.n += 1
        f = sub(self.p, "sequenceFlow", id=ncname("flow", self.n), sourceRef=a, targetRef=b, name=name)
        if cond:
            sub(f, "conditionExpression", cond).set("xsi:type", "tFormalExpression")

    def chain(self, ids: list[str]) -> None:
        for a, b in pairwise(ids):
            self.flow(a, b)


def to_bpmn(pack: Pack, process: ProcessDef, decision_id: str) -> str:
    root = ET.Element("definitions", {"xmlns": BpmnNs, "xmlns:xsi": XSI, "xmlns:camunda": CAMUNDA})
    root.set("id", ncname("definitions", process.key))
    root.set("targetNamespace", f"https://circularity.example/bpmn/{process.key}")
    p = sub(root, "process", id=ncname("process", process.key), name=f"{process.name} case process", isExecutable="false")
    sub(p, "documentation", LOSSY)
    b = _Builder(p)
    starts = []
    for i, label in enumerate(process.triggers, 1):
        starts.append(ncname("start", i))
        sub(p, "startEvent", id=starts[-1], name=label)
    stage = {s.key: s for s in pack.stages}

    def service(key: StageKey) -> str:
        sid = ncname("stage", key)
        t = sub(p, "serviceTask", id=sid, name=stage[key].label)
        sub(t, "documentation", f"Agent {stage[key].agent}, autonomy {stage[key].autonomy}.")
        if key in process.stage_sla_hours:
            ev = sub(p, "boundaryEvent", id=ncname("timer", key), name=f"{stage[key].label} is due", attachedToRef=sid,
                     cancelActivity="false")  # fmt: skip
            sub(sub(ev, "timerEventDefinition"), "timeDuration", _duration(process.stage_sla_hours[key]))
        return sid

    before = [service(k) for k in ("receive", "match", "condition", "value")]
    rules = ncname("task", "business_rules")
    sub(p, "businessRuleTask", id=rules, name="Apply business rules").set("camunda:decisionRef", decision_id)
    decide = service("decide")
    approvals = []
    for gid, owner, text in process.approvals:
        approvals.append(ncname("approve", gid))
        sub(sub(p, "userTask", id=approvals[-1], name=f"Approve: {gid}"), "documentation", f"{text} (owner {owner})")
    split, join = ncname("gateway", "routes"), ncname("gateway", "routes_join")
    sub(p, "exclusiveGateway", id=split, name="Route")
    sub(p, "exclusiveGateway", id=join, name="Routes join")
    after = [service("execute"), service("close")]
    end = ncname("end")
    sub(p, "endEvent", id=end, name="Case closed")
    for s in starts:
        b.flow(s, before[0])
    b.chain([*before, rules, decide, *approvals, split])
    for r in pack.routes:
        b.flow(split, join, r.name, f'route = "{r.id}"')
    b.chain([join, *after, end])
    return serialize(root)

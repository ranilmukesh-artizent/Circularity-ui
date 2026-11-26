"""Close only with reporting evidence (plan 9, P9-13.5, story X-16; gates G-REP-1 and G-REP-2 of the catalogue).

    Missing(gate_id, field, text)       one thing the facility has not reported yet
    close_check(case, pack, org)        what a case still lacks before it may close; [] when nothing, or no gate applies
    CODE_PATTERN                        the R or D treatment code (`R4`, `D10`)

A pack names the gates in `close.reporting`. G-REP-1 applies when the org unit is flagged `csrd_scope`: the case's
`case_material_report` evidence must hold mass in kilograms and the material. G-REP-2 applies when the chosen route is one of
the gate's route classes (recycle or exit): the case's `treatment_code` evidence must hold an R or D code. The evidence is
the case's `evidenceRecords` (I-3, `di.services.modeler.evidence`), as the facility reported it or a person attached it.
Pure: the caller reads the org flag. Never does: move a case, open an item or read the database (`actions/execution.py`).

Compliance text: the reporting rules (CSRD as amended, the Waste Framework Directive) are orientation only; Kinective's Legal
team reviews them before anyone relies on them.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from di.services.modeler.evidence import evidence_of
from di.services.modeler.gates import catalogue, gate_routes
from di.services.modeler.pack import Pack

CODE_PATTERN = re.compile(r"^[RD]\d{1,2}$")
CSRD, WASTE = "G-REP-1", "G-REP-2"
Field = Literal["mass_kg", "material", "treatment_code"]


@dataclass(frozen=True)
class Missing:
    gate_id: str
    field: Field
    text: str


def _route(case: Mapping[str, Any]) -> str:
    r = case.get("chosen") or case.get("recommendation") or {}
    return str(r.get("id") or "").split(":", 1)[0]


def _value(case: Mapping[str, Any], type: str) -> Mapping[str, Any]:
    e = evidence_of(case, type)
    return e.value if e is not None and e.result == "pass" else {}


def close_check(case: Mapping[str, Any], pack: Pack, org: Mapping[str, Any]) -> list[Missing]:
    """What the case still lacks, in the pack's gate order."""
    out: list[Missing] = []
    for gid in pack.close.reporting:
        if gid == CSRD and org.get("csrd_scope"):
            v = _value(case, "case_material_report")
            mass = v.get("mass_kg")
            if not isinstance(mass, int | float) or isinstance(mass, bool) or mass <= 0:
                out.append(Missing(gid, "mass_kg", f"mass in kilograms ({gid})"))
            if not str(v.get("material") or "").strip():
                out.append(Missing(gid, "material", f"material ({gid})"))
        elif gid == WASTE:
            gate = catalogue().get(gid)
            if gate is None or _route(case) not in gate_routes(gate, pack):
                continue
            if not CODE_PATTERN.match(str(_value(case, "treatment_code").get("code") or "")):
                out.append(Missing(gid, "treatment_code", f"treatment code ({gid})"))
    return out


def waiting_text(missing: list[Missing]) -> str:
    """The sentence the case and its work item show."""
    return "Waiting for reporting evidence: " + ", ".join(m.text for m in missing)

"""The personal and patient data gate `G-DATA-3` for the medical rental pack (plan 9, P9-11.17, story MR-19; registry entry I-2).
Pure.

    check_patient_data_sanitised(case, pack, gate) -> GateResult | None

A device of a class with patient data (`classes[].attrs.patient_data`, the patient monitor) must have a sanitisation record on
file before the disposal partner collects it: the case's `sanitisationRef` (the canonical `condition.sanitisation_record_ref`,
written by the disposal partner's adapter). Without it the result fails, effect `block`, `evidence_missing:
("sanitisation_record",)`, "Sanitisation record required before collection". The writer of `disposal_collection`
(`di.services.instructions.writers`) asks this check and does not send until it passes. Sanitisation is a step of the retire route
itself, so the gate is asked at the collection and never excludes the route at decision time.

The check answers only for the medical rental pack and, from P9-12.9, the medical capital pack (whose `routes` param names every
release route; its case's `sanitisationRef` comes from the fact `sanitisation_ref`): it returns None for a device with no patient data and for every other pack,
which keep the gate's evidence list (data wipe, controller sign-off). Never does: read the store, the clock or a session, or
write a case. HIPAA 45 CFR 164.310(d) and GDPR Art. 32 are the sources; the wording needs review by Kinective's Legal team before
it is relied on.
"""

# ruff: noqa: E501 - long sentence and SQL lines

from collections.abc import Mapping
from typing import Any

from di.services.modeler.evidence import records_of
from di.services.modeler.gates import CHECKS, GateDef, GateEffect, GateResult, _fact
from di.services.modeler.pack import Pack
from di.services.modeler.valuers.medical_steps import patient_data

GATE = "G-DATA-3"
PACK = "medical_rental"
PACKS = (PACK, "medical_capital")  # P9-12.9: imaging systems and patient monitors need the record before any release route
RECORD = "sanitisation_record"


def check_patient_data_sanitised(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-DATA-3 (module docstring); None leaves a device with no patient data, or another pack, to the data."""
    if pack.key not in PACKS or not patient_data(pack, case):
        return None
    ref = case.get("sanitisationRef")
    if ref:
        return GateResult(
            gate.id,
            True,
            GateEffect("block", (), gate.effect.hold_until_evidence, None),
            (),
            f"Sanitisation record {ref} on file",
        )
    routes = tuple(str(r) for r in gate.params.get("routes") or ())
    return GateResult(
        gate.id, False, GateEffect("block", routes, gate.effect.hold_until_evidence, None), (RECORD,),
        "Sanitisation record required before collection",
    )  # fmt: skip


CHECKS[GATE] = check_patient_data_sanitised


# ---------------------------------------------------------------- ITAD: sanitisation per media serial (P9-12.3, NS-IT-02)
# `G-DATA-1` and `G-DATA-2` for the `itad` pack (NIST SP 800-88 Rev. 2, IEEE 2883 summarised; Kinective's Legal team reviews the
# wording before it is relied on). The asset's `asset.media` ({mediaSerial, type: ssd | hdd}) are matched to its
# `condition.erasures` ({mediaSerial, method: clear | purge | destruct, verification: passed | failed}).
ITAD = "itad"
DATA_1, DATA_2 = "G-DATA-1", "G-DATA-2"
STEP_DESTRUCT = "destruct_media"
DESTRUCTION = "destruction_record"
LEAVING = ("return_to_lessor", "resell", "harvest", "recycle")  # routes that take the asset out of the owner's control
NO_PARTS = "Media failed verification: no parts sale"
NOT_INVENTORIED = "Media not inventoried: sanitisation record required"
_STRONG = ("purge", "destruct")
_ENOUGH = {"ssd": _STRONG, "hdd": ("clear", *_STRONG)}  # what lets a media type leave


def _records(case: Mapping[str, Any], pack: Pack, path: str) -> list[Mapping[str, Any]]:
    v = _fact(case, pack, path)
    return [x for x in v if isinstance(x, Mapping)] if isinstance(v, list) else []


def _problem(media: Mapping[str, Any], erasures: list[Mapping[str, Any]], leaves: bool) -> str | None:
    """Why one media serial does not allow the route (None when it does): no record, a failed verification, or too weak a method."""
    serial = str(media.get("mediaSerial"))
    mine = [e for e in erasures if str(e.get("mediaSerial")) == serial]
    if not mine:
        return f"Sanitisation record missing for media {serial}"
    kind = str(media.get("type") or "hdd")
    need = _ENOUGH.get(kind, _STRONG) if leaves else ("clear", *_STRONG)
    if any(e.get("verification") == "passed" and e.get("method") in need for e in mine):
        return None
    if any(e.get("verification") == "failed" for e in mine):
        return f"Sanitisation of media {serial} failed verification"
    methods = ", ".join(sorted({str(e.get("method")) for e in mine}))
    return f"Media {serial} ({kind}) is only {methods}: {' or '.join(need)} needed" + (" to leave" if leaves else "")


def media_facts(case: Mapping[str, Any], pack: Pack) -> dict[str, Any]:
    """The derived fact `media.sanitisable` that triggers G-DATA-2: False when any erasure failed its verification. Empty for
    another pack or an asset with no media records."""
    if pack.key != ITAD or not _records(case, pack, "asset.media"):
        return {}
    failed = any(e.get("verification") == "failed" for e in _records(case, pack, "condition.erasures"))
    return {"sanitisable": not failed}


def _same_owner_and_level(case: Mapping[str, Any], pack: Pack) -> bool:
    """A redeploy stays inside the owner's control when the request's owner and security level (facts `request.owner_org`,
    `request.security_level`, when the request names them) are the asset's."""
    for mine, theirs in (("asset.owner_org", "request.owner_org"), ("asset.security_level", "request.security_level")):
        want = _fact(case, pack, theirs)
        if want is not None and want != _fact(case, pack, mine):
            return False
    return True


def _class_has_media(case: Mapping[str, Any], pack: Pack) -> bool:
    """The asset's class has media (`class.has_media`); the class is the case's `cls`, else the CMDB's `asset.asset_class`."""
    cls = case.get("cls") or _fact(case, pack, "asset.asset_class")
    found = next((c for c in pack.classes if c.id == cls), None)
    return bool(found and found.attrs.has_media)


def check_media_sanitised(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-DATA-1: every media serial needs an erasure record; a route leaving the owner's control needs `purge` or `destruct` for an
    `ssd` and at least `clear` for an `hdd`, verified; a redeploy inside the same owner and level accepts `clear` for any type. A
    failing route says which media (its own reason); a harvest of failed media says "no parts sale". An asset of a class with
    media but no media list fails every route that leaves the owner's control (NOT_INVENTORIED; review P9-12.13 F1). The result
    never holds the case: the routes fail and a new record is read by the next decision. None for another pack or an asset of a
    class with no media and no media list."""
    if pack.key != ITAD:
        return None
    media = _records(case, pack, "asset.media")
    ids = {r.id for r in pack.routes}
    leaving = [r for r in (gate.params.get("routes") or LEAVING) if r in ids]
    stays = _same_owner_and_level(case, pack)
    if not media:
        if not _class_has_media(case, pack):
            return None
        shut = [*(["redeploy"] if "redeploy" in ids and not stays else []), *leaving]
        return GateResult(
            gate.id, False, GateEffect("block", tuple(shut), False, None), (), NOT_INVENTORIED,
            route_reasons=tuple((r, NOT_INVENTORIED) for r in shut),
        )  # fmt: skip
    erasures = _records(case, pack, "condition.erasures")
    failed = any(e.get("verification") == "failed" for e in erasures)
    reasons: list[tuple[str, str]] = []
    for rid in [*(["redeploy"] if "redeploy" in ids else []), *leaving]:
        why = next((p for m in media if (p := _problem(m, erasures, leaves=rid != "redeploy" or not stays))), None)
        if why and failed and rid == "harvest":
            why = NO_PARTS
        if why:
            reasons.append((rid, why))
    if not reasons:
        return GateResult(
            gate.id, True, GateEffect("block", (), False, None), (), "Sanitisation record on file for every media serial"
        )
    return GateResult(
        gate.id, False, GateEffect("block", tuple(r for r, _ in reasons), False, None), (), reasons[0][1],
        route_reasons=tuple(reasons),
    )  # fmt: skip


def _destroyed(case: Mapping[str, Any]) -> set[str]:
    """The media serials a passed `destruction_record` names (its value's `mediaSerial`)."""
    return {
        str(e.value["mediaSerial"])
        for e in records_of(case)
        if e.type == DESTRUCTION and e.result == "pass" and e.value.get("mediaSerial")
    }


def check_sanitisation_verified(case: Mapping[str, Any], pack: Pack, gate: GateDef) -> GateResult | None:
    """G-DATA-2: media whose verification `failed` require the step `destruct_media` (effect `require_step`) until a passed
    `destruction_record` naming that media serial is on file, one per failed serial (a record of other media, or a failed one,
    does not clear it; review P9-12.13 F2). None for another pack, with no failed media, or once every one is destroyed."""
    if pack.key != ITAD:
        return None
    gone = _destroyed(case)
    failed = list(
        dict.fromkeys(
            s
            for e in _records(case, pack, "condition.erasures")
            if e.get("verification") == "failed" and (s := str(e.get("mediaSerial"))) not in gone
        )
    )
    if not failed:
        return None
    ids = {r.id for r in pack.routes}
    routes = tuple(r for r in LEAVING if r in ids)
    return GateResult(
        gate.id, False, GateEffect("require_step", routes, False, STEP_DESTRUCT), (DESTRUCTION,),
        f"Media failed verification: destroy {', '.join(failed)}",
    )  # fmt: skip


CHECKS[DATA_1] = check_media_sanitised
CHECKS[DATA_2] = check_sanitisation_verified

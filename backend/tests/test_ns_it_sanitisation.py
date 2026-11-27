"""P9-12.3 (stories NS-IT-02, NS-IT-03): sanitisation per media serial and the residual value that decays by month.

G-DATA-1 (every media serial of the asset needs an erasure record; to leave the owner's control an SSD needs purge or destruct,
an HDD at least clear, both verified; redeploy inside the same owner and level accepts clear). G-DATA-2 (a failed verification
requires the step `destruct_media`, and a harvest of that media fails). Resale value = new price x residual start by class,
decayed 3 percent a month over the months in stock (standard valuer `decay`). SR-IT-AGE: stock of 2 months or more is suggested
for wholesale, oldest first. Synthetic data. The gate wording is a research summary of NIST SP 800-88 Rev. 2: Kinective's Legal
team must review it before it is relied on."""

from tests import itkit

LEAVING = ("return_to_lessor", "resell", "harvest", "recycle")


def _gate(d, gate_id):
    return next(g for g in d.gates if g.gate_id == gate_id)


def test_ns_it_02_ssd_needs_purge_to_leave():
    d = itkit.decide(itkit.case("IT-S2"))
    g = _gate(d, "G-DATA-1")
    assert not g.passed and set(g.effect.routes) == set(LEAVING) and "redeploy" not in g.effect.routes
    for rid in ("resell", "harvest", "recycle"):
        r = itkit.route(d, rid)
        assert r["excluded"] and "MS-S-1" in r["failReason"], (rid, r["failReason"])
    assert itkit.route(d, "return_to_lessor")["excluded"]  # the lease does not ask for it either
    assert not itkit.route(d, "redeploy")["excluded"]  # inside the same owner and level, clear is enough
    assert d.route == "redeploy"


def test_ns_it_02_missing_record_names_the_media():
    c = itkit.case("IT-S1")
    c["condition"] = {"erasures": []}
    d = itkit.decide(c)
    assert "Sanitisation record missing for media MS-S-1" in itkit.route(d, "resell")["failReason"]
    assert itkit.route(d, "redeploy")["excluded"]  # no record at all: not even a redeploy


def test_ns_it_02_hdd_clear_is_enough_to_leave_and_ssd_purge_passes():
    assert _gate(itkit.decide(itkit.case("IT-S5")), "G-DATA-1").passed  # two hard disks, cleared and verified
    assert _gate(itkit.decide(itkit.case("IT-S1")), "G-DATA-1").passed  # one SSD, purged


def test_ns_it_02_failed_verification_destructs():
    d = itkit.decide(itkit.case("IT-S3"))
    g2 = _gate(d, "G-DATA-2")
    assert not g2.passed and (g2.effect.kind, g2.effect.step) == ("require_step", "destruct_media")
    assert "destruct_media" in [s.get("step") for s in d.required_steps]
    harvest = itkit.route(d, "harvest")
    assert harvest["excluded"] and "Media failed verification: no parts sale" in harvest["failReason"]
    assert itkit.route(d, "resell")["excluded"]  # a failed verification is no record that lets it leave


def test_ns_it_02_destruction_record_clears_the_step():
    c = itkit.case("IT-S3")
    c["evidenceRecords"] = [{"type": "destruction_record", "source": "it_logistics", "at": "2026-11-01T00:00:00+00:00",
                             "result": "pass", "value": {"mediaSerial": "MS-S-1"}}]  # fmt: skip
    assert _gate(itkit.decide(c), "G-DATA-2").passed


def test_ns_it_02_media_not_inventoried_fails_the_leaving_routes():
    """Review P9-12.13 F1: an asset of a class with media but no media list cannot leave without a sanitisation record."""
    from di.services.modeler.gate_checks.data import check_media_sanitised
    from di.services.modeler.gates import pack_gates

    for media in (None, []):
        c = itkit.case("IT-S1")
        if media is None:
            del c["asset"]["media"]
        else:
            c["asset"]["media"] = media
        d = itkit.decide(c)
        g = _gate(d, "G-DATA-1")
        assert not g.passed and set(g.effect.routes) == set(LEAVING), (media, g)
        for rid in ("resell", "harvest", "recycle"):  # return_to_lessor fails first: the lease does not ask for it
            assert "Media not inventoried: sanitisation record required" in itkit.route(d, rid)["failReason"], rid
        assert not itkit.route(d, "redeploy")["excluded"]  # inside the same owner and level it stays open
    c = itkit.case("IT-S1")  # a redeploy to another owner leaves the owner's control
    c["request"] = {"owner_org": "Customer B"}
    del c["asset"]["media"]
    assert "redeploy" in _gate(itkit.decide(c), "G-DATA-1").effect.routes
    network = itkit.case("IT-S6")  # a class with no media: unchanged
    del network["asset"]["media"]
    gate = next(g for g in pack_gates(itkit.pack()) if g.id == "G-DATA-1")
    assert check_media_sanitised(network, itkit.pack(), gate) is None


def test_ns_it_02_destruction_record_must_name_the_failed_media_and_pass():
    """Review P9-12.13 F2: only a passed destruction record of the failed media serial clears G-DATA-2."""
    at = "2026-11-01T00:00:00+00:00"
    for value, result in (({"mediaSerial": "MS-OTHER"}, "pass"), ({"mediaSerial": "MS-S-1"}, "fail"), ({}, "pass")):
        c = itkit.case("IT-S3")
        c["evidenceRecords"] = [{"type": "destruction_record", "source": "it_logistics", "at": at, "result": result,
                                 "value": value}]  # fmt: skip
        g2 = _gate(itkit.decide(c), "G-DATA-2")
        assert not g2.passed and "MS-S-1" in g2.reason, (value, result)


def test_ns_it_03_residual_decays_monthly():
    def resale(months: int) -> float:
        d = itkit.decide(itkit.case("IT-S7", asset__months_in_stock=months))
        return next(t["amt"] for t in itkit.route(d, "resell")["terms"] if t["label"] == "Resale value")

    assert resale(4) == 433.79  # 1,400 x 0.35 x 0.97^4
    assert resale(5) == 420.78


def test_ns_it_03_ageing_stock_suggests_wholesale():
    from di.services.cases import itad_ageing

    stock = [
        {"serial": "SN-A", "asset_class": "laptop", "months_in_stock": 2},
        {"serial": "SN-B", "asset_class": "laptop", "months_in_stock": 3},
        {"serial": "SN-C", "asset_class": "laptop", "months_in_stock": 1},
    ]
    got = itad_ageing.suggestions(itkit.pack(), stock)
    assert [(s["serial"], s["route"]) for s in got] == [("SN-B", "resell"), ("SN-A", "resell")]
    assert all(s["rule"] == "SR-IT-AGE" and "wholesale" in s["text"] for s in got)

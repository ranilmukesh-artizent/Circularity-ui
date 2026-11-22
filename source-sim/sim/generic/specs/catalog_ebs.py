"""Oracle E-Business Suite (catalogue): supplier invoices and payables from the legacy ERP, for Reconcile. Synthetic;
reads like the EBS Integrated SOA Gateway REST services (snake_case AP columns, `items`, limit / offset). Basic auth."""

from sim.generic.catalog import ago, facts, h, iso, pick
from sim.generic.spec import Auth, Paging, Resource, Spec
from sim.seed import Seed

SUPPLIERS = (("2001", "Sims Lifecycle Services"), ("2002", "EcoParts Recovery"), ("2003", "MetalCycle Ltd"),
             ("2004", "Reman Co"), ("2005", "Northfield Logistics"))  # fmt: skip


def seed(s: Seed) -> dict[str, list[dict]]:
    suppliers = [
        {"vendor_id": vid, "vendor_name": name, "segment1": f"SUP{vid}", "enabled_flag": "Y",
         "invoice_currency_code": pick(("INR", "USD", "EUR"), vid)}
        for vid, name in SUPPLIERS
    ]  # fmt: skip
    invoices = []
    for n, f in enumerate(f for f in facts(s) if h(f.id, "ebs") % 2 == 0):
        vid, _ = pick(SUPPLIERS, f.id, "v")
        invoices.append(
            {"invoice_id": str(880000 + n), "invoice_num": f"INV-{f.id}", "vendor_id": vid,
             "invoice_amount": round(100 + h(f.id, "amt") % 9000 + (h(f.id, "c") % 100) / 100, 2),
             "invoice_currency_code": pick(("INR", "USD", "EUR"), vid),
             "status": pick(("VALIDATED", "NEEDS REVALIDATION", "PAID"), f.id),
             "description": f"Recovery services {f.asset_id}", "invoice_date": ago(s, f.id, "inv").date().isoformat(),
             "last_update_date": iso(ago(s, f.id, "upd", days=20))}
        )  # fmt: skip
    return {"invoices": invoices, "suppliers": suppliers}


SPEC = Spec(
    source_id="ebs",
    title="Oracle E-Business Suite",
    schema="cat_ebs",
    base_path="/ebs/webservices/rest/ap",
    auth=Auth("basic"),
    paging=Paging("offset", items_key="items", next_key="next_offset", total_key="totalResults", max_size=100),
    resources=(
        Resource("invoices", "/invoices", "invoice_id", filters=("vendor_id", "status")),
        Resource("suppliers", "/suppliers", "vendor_id"),
    ),
    seed=seed,
)

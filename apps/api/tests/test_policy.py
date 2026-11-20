"""B7 parity: the server's access policy gives the demo's answers for every account (fixtures/golden/figures.json)."""

import pytest

from di import policy
from di.golden import load

FIGURES = load("figures")["accounts"]
CASES = load("cases")
ACCOUNT_IDS = sorted(FIGURES)


def test_all_eleven_accounts():
    assert sorted(a.id for a in policy.accounts()) == ACCOUNT_IDS and len(ACCOUNT_IDS) == 11


@pytest.mark.parametrize("account_id", ACCOUNT_IDS)
def test_permissions(account_id):
    a = policy.account(account_id)
    assert {p: policy.can(a, p) for p in FIGURES[account_id]["can"]} == FIGURES[account_id]["can"]


@pytest.mark.parametrize("account_id", ACCOUNT_IDS)
def test_pages_and_sections(account_id):
    a = policy.account(account_id)
    for page, golden in FIGURES[account_id]["pages"].items():
        assert policy.can_page(a, page) == ("" in golden), page
        expected = [s for s in golden if s]
        assert [s for s in policy.sections().get(page, []) if policy.can_page(a, page, s)] == expected, page


@pytest.mark.parametrize("account_id", ACCOUNT_IDS)
def test_tenants_home_and_visible_cases(account_id):
    a = policy.account(account_id)
    g = FIGURES[account_id]
    assert policy.allowed_tenants(a) == g["allowed_tenants"]
    assert policy.home(a) == g["home"]
    visible = sorted(c["id"] for c in CASES if policy.tenant_ok(a, c["owner"]) and policy.location_ok(a, c["location"]))
    assert visible == g["visible_case_ids"]


def test_approver_delegations_switch_approval_rights():
    approver = policy.account("approver")
    off = policy.Context(delegations={"decisions": False, "mcp": True, "tenantAccess": True})
    assert policy.can(approver, "approve.decisions") and not policy.can(approver, "approve.decisions", off)
    assert policy.can(approver, "approve.mcp", off)
    assert policy.can(policy.account("admin"), "approve.decisions", off)  # Admin is never limited by delegations


def test_tenant_grants_widen_a_planner():
    planner = policy.account("planner-b")
    ctx = policy.Context(grants={"planner-b": ["Customer A"]})
    assert policy.allowed_tenants(planner) == ["Customer B"]
    assert policy.allowed_tenants(planner, ctx) == ["Customer A", "Customer B"]


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("exec", "executive"),
        ("OPS", "planner-a"),
        ("planner.b@northfield.example", "planner-b"),
        ("warehouse2", "wm-2"),
        ("admin@northfield.example", "admin"),
        ("someone@elsewhere.com", None),
        ("", None),
        ("nobody", None),
    ],
)
def test_sign_in_ids(typed, expected):
    a = policy.resolve_sign_in(typed)
    assert (a.id if a else None) == expected

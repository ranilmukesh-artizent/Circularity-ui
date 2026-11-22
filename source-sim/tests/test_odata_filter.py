import pytest
from sqlalchemy import Column, DateTime, MetaData, Numeric, String, Table
from sqlalchemy.dialects import postgresql

from sim.vendors.s4.odata.filter import FilterError, parse_filter

T = Table(
    "t",
    MetaData(),
    Column("Plant", String),
    Column("Material", String),
    Column("Qty", Numeric),
    Column("Changed", DateTime(timezone=True)),
)
COLS = {c.name: c for c in T.c}


def sql(f: str) -> str:
    return str(parse_filter(f, COLS).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("Plant eq '1030'", "t.\"Plant\" = '1030'"),
        ("Qty gt 5", 't."Qty" > 5'),
        ("Qty le 5.5M", 't."Qty" <= 5.5'),
        ("Material ne null", 't."Material" IS NOT NULL'),
        ("Plant eq 'O''Neil'", "t.\"Plant\" = 'O''Neil'"),
        ("Plant eq '1030' and Qty gt 0", 't."Plant" = \'1030\' AND t."Qty" > 0'),
        ("(Plant eq '1030' or Plant eq '2010') and Qty gt 0", '(t."Plant" = \'1030\' OR t."Plant" = \'2010\') AND t."Qty" > 0'),
        ("not (Plant eq '1030')", "t.\"Plant\" != '1030'"),
        ("'1030' eq Plant", "t.\"Plant\" = '1030'"),
    ],
)
def test_translates(expr, expected):
    assert sql(expr) == expected


def test_string_functions():
    for f in ("substringof('MTR',Material)", "substringof('MTR',Material) eq true"):
        out = sql(f)
        assert "LIKE" in out and "NOT LIKE" not in out and "'MTR'" in out and "%" in out
    assert "NOT LIKE" in sql("startswith(Material,'MTR') eq false")
    assert "NOT LIKE" in sql("substringof('MTR',Material) eq false")


def test_datetimeoffset_literal():
    out = sql("Changed gt datetimeoffset'2026-10-07T09:00:00Z'")
    assert out.startswith('t."Changed" > ') and "2026-10-07 09:00:00+00:00" in out


@pytest.mark.parametrize(
    "bad", ["Nope eq 1", "Plant eq", "Plant eq '1' and", "Plant = '1'", "Plant eq '1')", "startswith(Material,'M') gt 1"]
)
def test_rejects(bad):
    with pytest.raises(FilterError):
        parse_filter(bad, COLS)

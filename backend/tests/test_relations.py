"""Medicine relationship groupings (alternatives / other forms / other strengths).

These tests cross-check the API output against direct SQL over the real
catalog, so a regression in the grouping rules fails loudly.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

DB = Path(__file__).resolve().parents[2] / "data" / "banglamed.db"

# One real brand per major dosage form, plus a NULL-strength and NULL-generic case.
SAMPLES = [8381, 8379, 7984, 18254, 1415, 23112, 18217, 7588, 4330, 8010, 7531, 511, 2001]


def _norm(s: str | None) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def _root(n: str | None) -> str:
    return (n or "").strip().split(" ")[0].lower()


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(DB)
    yield c
    c.close()


def _truth(conn, bid: int):
    """Recompute the four groups from SQL, independently of the service code."""
    row = conn.execute(
        "select name, strength_text, form_name, generic_id from brands where id=?", (bid,)
    ).fetchone()
    assert row, f"brand {bid} missing"
    name, st, form, gid = row
    groups = {"alt": set(), "forms": set(), "str": set(), "fam": set()}
    if gid is None:
        return groups
    my_s, my_f, my_r = _norm(st), (form or "").strip().lower(), _root(name)
    for i, n, s, f in conn.execute(
        "select id, name, strength_text, form_name from brands where generic_id=? and id!=?",
        (gid, bid),
    ):
        same_s, same_f = _norm(s) == my_s, (f or "").strip().lower() == my_f
        if same_s and same_f:
            groups["alt"].add(i)
        elif same_s:
            groups["forms"].add(i)
        elif same_f:
            groups["str"].add(i)
        elif my_r and _root(n) == my_r:
            groups["fam"].add(i)
    return groups


@pytest.mark.parametrize("bid", SAMPLES)
def test_groups_match_sql_truth(client, conn, bid):
    d = client.get(f"/api/medicines/{bid}").json()
    t = _truth(conn, bid)
    assert {x["id"] for x in d["alternatives"]} == t["alt"]
    assert {x["id"] for x in d["other_forms"]} == t["forms"]
    assert {x["id"] for x in d["other_strengths"]} == t["str"]
    assert {x["id"] for x in d["brand_family"]} == t["fam"]


@pytest.mark.parametrize("bid", SAMPLES)
def test_counts_are_truthful_and_never_truncate_silently(client, bid):
    """Each count must equal the true group size and be >= the returned list."""
    d = client.get(f"/api/medicines/{bid}").json()
    for list_key, count_key in (
        ("alternatives", "alternatives_count"),
        ("other_forms", "other_forms_count"),
        ("other_strengths", "other_strengths_count"),
        ("brand_family", "brand_family_count"),
    ):
        assert d[count_key] >= len(d[list_key]), f"{count_key} smaller than its list"
        # Every returned row must belong to the same generic as the page brand.
        for row in d[list_key]:
            assert row["generic_id"] == d["brand"]["generic_id"]


@pytest.mark.parametrize("bid", SAMPLES)
def test_groups_are_mutually_exclusive_and_never_self_referencing(client, bid):
    d = client.get(f"/api/medicines/{bid}").json()
    A = {x["id"] for x in d["alternatives"]}
    F = {x["id"] for x in d["other_forms"]}
    S = {x["id"] for x in d["other_strengths"]}
    assert not (A & F), "a brand appears in both alternatives and other_forms"
    assert not (A & S), "a brand appears in both alternatives and other_strengths"
    assert not (F & S), "a brand appears in both other_forms and other_strengths"
    assert bid not in (A | F | S), "the page's own brand appears in its own relations"


def test_azithromycin_alternatives_are_not_truncated(client):
    """Regression: the old query did `.limit(30)` over all same-generic brands
    and reported no total, so a 125-row group silently showed only 30."""
    d = client.get("/api/medicines/8381").json()
    assert d["alternatives_count"] == 125
    assert len(d["alternatives"]) == 125
    assert d["same_generic_total"] == 331


def test_null_strength_brand_gets_null_safe_alternatives(client):
    """`strength_text == NULL` never matches in SQL; the service must still
    group two brands that both have no recorded strength."""
    d = client.get("/api/medicines/511").json()
    assert d["brand"]["strength"] is None
    assert {x["id"] for x in d["alternatives"]} == {512}


def test_brand_without_generic_has_empty_groups(client):
    d = client.get("/api/medicines/802").json()
    assert d["brand"]["generic"] is None
    assert d["alternatives"] == [] and d["other_forms"] == []
    assert d["other_strengths"] == [] and d["brand_family"] == []
    assert d["alternatives_count"] == 0


def test_alternatives_endpoint_agrees_with_detail(client):
    detail = client.get("/api/medicines/8381").json()
    alts = client.get("/api/medicines/8381/alternatives").json()
    assert {x["id"] for x in alts["alternatives"]} == {x["id"] for x in detail["alternatives"]}
    assert alts["alternatives_count"] == detail["alternatives_count"]


def test_strength_normalisation_merges_formatting_variants(client, conn):
    """'0.2% + 0.5%' and '0.2%+0.5%' are the same strength and must group."""
    gid = conn.execute(
        "select generic_id from brands where id=8381"
    ).fetchone()[0]
    # find a generic that genuinely has whitespace-variant strengths
    row = conn.execute(
        """select generic_id, form_name from brands
           where strength_text like '% %+% ' or strength_text like '% + %'
           group by generic_id, form_name having count(distinct strength_text) > 1 limit 1"""
    ).fetchone()
    if not row:
        pytest.skip("no whitespace-variant strengths in this catalog")
    g, f = row
    my = conn.execute(
        "select id, strength_text from brands where generic_id=? and form_name=? limit 1", (g, f)
    ).fetchone()
    d = client.get(f"/api/medicines/{my[0]}").json()
    for x in d["alternatives"]:
        assert _norm(x["strength"]) == _norm(my[1])

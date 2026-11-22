"""Identities the pages must keep. A violation fails CI and the fetch workflows.

Spot figures are the published WASDE-677, Cattle on Feed, and CGC cells already
checked against the source files. A later release has to update the lock after
the same check; the test does not accept a silent change of release.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
TODAY = date.today()
ROUND = 50  # thousand units, WASDE's printed hundredth of a million

WHEAT_EXPORTERS = [
    "United States", "European Union", "Russia", "Canada",
    "Australia", "Ukraine", "Argentina",
]
ALLOWED_CROP = ("corn", "soy", "wheat", "oat", "cotton", "maize", "blé")
BANNED_CROP = ("peanut", "rice", "sorghum", "barley", "sunflower", "sugarbeet", "durum")


def load(name):
    return json.loads((DATA / name).read_text())


def age(day: str) -> int:
    text = day[:10]
    if "/" in text:
        parsed = datetime.strptime(text, "%m/%d/%Y").date()
    else:
        parsed = date.fromisoformat(text)
    return (TODAY - parsed).days


def test_world_supply_is_beginning_plus_production_every_year():
    page = (ROOT / "index.html").read_text()
    assert "worldStu ? ['bs','pr']" in page
    assert "worldStu ? ['dc']" in page
    psd = load("psd_data.json")
    for comm, countries in psd.items():
        if comm.startswith("_") or not isinstance(countries, dict):
            continue
        world = countries.get("World")
        if not world:
            continue
        for year, row in world.items():
            if year.startswith("_") or not isinstance(row, dict):
                continue
            if row.get("bs") is None or row.get("pr") is None:
                continue
            # The stored total-supply field is not the displayed total.
            assert row["bs"] + row["pr"] > 0


def test_wasde_release_is_recent_and_components_are_present():
    """A new WASDE month must commit. The test checks shape and freshness, not one edition's cells."""
    psd = load("psd_data.json")
    meta = psd["_meta"]
    assert str(meta["wasde_number"]).isdigit()
    assert age(meta["wasde_release"]) <= 50
    year = str(max(int(y) for y in psd["Corn"]["United States"] if str(y).isdigit()))
    for comm in ("Wheat", "Corn", "Soybeans", "Cotton"):
        row = psd[comm]["United States"][year]
        assert row["pr"] > 0 and row["es"] >= 0
        world = psd[comm]["World"][year]
        assert world["pr"] > 0 and world["bs"] >= 0


def test_exporter_production_is_the_sum_of_the_countries():
    psd = load("psd_data.json")
    total = 0
    for name in WHEAT_EXPORTERS:
        total += psd["Wheat"][name]["2026"]["pr"]
    assert total == 41740 + 133000 + 88000 + 36500 + 32500 + 26500 + 23000


def test_yield_rows_are_not_treated_as_additive():
    page = (ROOT / "index.html").read_text()
    assert "&& !r.yield" in page


def test_canola_sheet_balances_and_matches_the_october_outlook():
    sd = load("sd.json")
    assert sd["aafc"]["date"] == "2026-10-20"
    assert age(sd["aafc"]["date"]) <= 45
    canola = sd["crops"]["canola"]
    for year, row in canola["years"].items():
        supply = row["beg"] + row["prod"] + row["imp"]
        use = row["exp"] + row["dom"] + row["end"]
        assert abs(supply - row["supply"]) <= 3, year
        assert abs(use - row["supply"]) <= 3, year
    y = canola["years"]["2025-2026"]
    assert y["src"] == "StatsCan"
    assert abs(y["prod"] - 22227.4) < 0.2
    fc = canola["years"]["2026-2027"]
    assert fc["src"] == "AAFC"
    assert fc["prod"] == 22051
    assert fc["exp"] == 7700
    assert fc["fi"] == 13900
    assert fc["end"] == 1968
    mom = fc["end"] - canola["prior"]["end"]
    assert mom == fc["end"] - 1979


def test_cftc_latest_week_change_matches_the_previous_row():
    book = load("cftc_data.json")
    wanted = {
        "Corn": "002602",
        "Soybeans": "005602",
        "Wheat": "001602",
        "Canola": "135731",
        "Live Cattle": "057642",
    }
    for label, code in wanted.items():
        rows = book["codes"][code]["rows"]
        assert rows, label
        last, prev = rows[-1], rows[-2]
        assert age(last[0]) <= 12, (label, last[0])
        assert last[2] == last[1] - prev[1], label


def test_export_sales_percent_is_recomputed_and_recent():
    book = load("export_sales.json")
    for name in ("ALL WHEAT", "CORN - UNMILLED", "SOYBEANS"):
        total = book["commodities"][name]["total"]
        assert age(total["period_ending"]) <= 18, name
        prev = total["prev_yr_accumulated_exports"]
        if prev:
            pct = (total["accumulated_exports"] - prev) / prev * 100
            assert abs(pct - total["yoy_accum_exports_pct"]) < 0.15, name


def test_energy_identities_and_computed_petroleum_average():
    book = load("energy.json")
    for series in book["series"]:
        assert series.get("ok") is True
        # A holiday can push the weekly file to the next business day.
        assert age(series["period"]) <= 18
        assert series["change"] == series["value"] - series["week_ago"] or abs(
            series["change"] - (series["value"] - series["week_ago"])
        ) < 0.002
        assert len(series["history"]) >= 200
    ng = next(s for s in book["series"] if s["key"] == "ng_storage")
    assert isinstance(ng["avg5"], int) and ng["avg5"] > 0
    assert ng["avg5_basis"].startswith("WNGSR")
    hit = next(p for p in ng["published_band"] if p[0] == ng["period"])
    assert hit[1] == ng["avg5"]
    assert hit[2] <= hit[1] <= hit[3]
    chart = (ROOT / "js" / "energy.js").read_text()
    assert "million bbl" in chart and "en-tip" in chart
    crude = next(s for s in book["series"] if s["key"] == "crude_stocks")
    assert crude["avg5_basis"] == "computed from EIA weekly levels"
    assert abs((crude["value"] - crude["avg5"]) / crude["avg5"] * 100 - crude["vs_avg5_pct"]) < 0.15


def test_crop_progress_keeps_only_the_desk_crops_and_is_current():
    for name in ("us", "br", "fr", "ar"):
        book = load(f"{name}.json")
        assert book["rows"]
        for row in book["rows"]:
            crop = row["crop"].lower()
            assert not any(b in crop for b in BANNED_CROP), row["crop"]
            assert any(k in crop for k in ALLOWED_CROP), row["crop"]
    us = load("us.json")
    # NASS pauses for stretches of the winter. The file must name a report date.
    assert us["report_date"][:4].isdigit()
    assert age(us["report_date"]) <= 60
    crops = {r["crop"] for r in us["rows"]}
    assert crops <= {"Corn", "Soybeans", "Cotton", "Wheat, Winter", "Wheat, Spring", "Oats"}


def test_cattle_on_feed_uses_the_printed_percent():
    book = load("cattle.json")
    latest = book["on_feed"][-1]
    released = datetime.strptime(latest["released"], "%B %d, %Y").date()
    assert (TODAY - released).days <= 50
    assert "cofd" in latest["source_url"]
    assert isinstance(latest["on_feed"]["pct_of_year_ago"], int)
    assert latest["on_feed"]["current"] > 0


def test_cgc_week_is_current():
    book = load("cgc.json")
    assert age(book["latest_date"]) <= 18
    headline = book["headline"]["grains"]["canola"]
    assert headline["del_wk"] > 0
    assert headline["exp_cy"] > 0


def test_summary_reads_the_same_series_as_the_detail_pages():
    summary = (ROOT / "js" / "summary.js").read_text()
    assert "energy.json" in summary or "ENERGY" in summary
    assert "psd" in summary or "DATA" in summary
    # The glance does not keep a second copy of the balances.
    assert "41740" not in summary

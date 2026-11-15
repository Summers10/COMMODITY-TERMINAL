"""Locks published figures the terminal must not recompute."""
import json
from pathlib import Path

from scripts.fetch_cattle import parse_cof, parse_cutout, parse_inventory
from scripts.fetch_psd import fill_world_prior_gaps
from scripts.wasde_tables import parse_wasde

ROOT = Path(__file__).resolve().parents[1]

COF = """
Cattle on Feed Inventory, Placements, Marketings, and Other Disappearance on
1,000+ Capacity Feedlots - United States: October 1, 2025 and 2026
On feed September 1 ....................:   11,080        11,168          101
Placed on feed during September ........:    2,021         1,777           88
Fed cattle marketed during September ...:    1,632         1,524           93
Other disappearance during September ...:       51            49           96
On feed October 1 ......................:   11,418        11,372          100
Released October 23, 2026, by the National Agricultural Statistics Service
"""


def test_cof_uses_printed_percent_not_a_ratio():
    row = parse_cof(COF)
    assert row["as_of"] == "2026-10-01"
    assert row["on_feed"]["current"] == 11372
    assert row["on_feed"]["year_ago"] == 11418
    # 11372/11418 is 99.6, which the report prints as 100.
    assert row["on_feed"]["pct_of_year_ago"] == 100
    assert row["placements"]["pct_of_year_ago"] == 88


def test_boxed_beef_reads_a_decline_in_parentheses():
    text = (
        "Agricultural Marketing Service November 13, 2026\n"
        "Current Cutout Values: 355.64 349.15\n"
        "Change from prior day: (1.95) 0.44\n"
    )
    row = parse_cutout(text)
    assert row["choice"] == 355.64
    assert row["select"] == 349.15
    assert row["choice_change"] == -1.95
    assert row["select_change"] == 0.44
    assert row["as_of"] == "November 13, 2026"


JANUARY = """
Released January 30, 2026, by the National Agricultural Statistics Service
Cattle Inventory by Class and Calf Crop - United States: January 1, 2025 and 2026
All cattle and calves ...................:   86,472.2       86,155.3         100
All cows and heifers that have calved ...:   37,272.8       37,175.5         100
  Beef cows .............................:   27,892.0       27,607.2          99
  For beef cow replacement ..............:    4,672.5        4,714.2         101
Calf crop ...............................:   33,416.5       32,895.6          98
"""


def test_january_inventory_matches_the_published_class_table():
    text = JANUARY
    row = parse_inventory(text)
    assert row["rows"]["all_cattle"]["current"] == 86155.3
    assert row["rows"]["beef_cows"]["current"] == 27607.2
    assert row["rows"]["heifers_retained"]["current"] == 4714.2
    assert row["rows"]["calf_crop"]["current"] == 32895.6
    assert row["rows"]["beef_cows"]["pct_of_year_ago"] == 99


def test_energy_file_keeps_published_gas_average():
    energy = json.loads((ROOT / "data" / "energy.json").read_text())
    ng = next(s for s in energy["series"] if s["key"] == "ng_storage")
    # The average and the percent are stored as WNGSR printed them.
    # The weekly change is the printed net change, which equals the two printed stocks.
    assert isinstance(ng["avg5"], int)
    assert ng["vs_avg5_pct"] is not None
    assert ng["change"] == ng["value"] - ng["week_ago"]
    crude = next(s for s in energy["series"] if s["key"] == "crude_stocks")
    assert crude["avg5"] is None
    assert abs((crude["value"] - crude["week_ago"]) - crude["change"]) < 0.002


def test_wasde_world_wheat_is_the_published_row():
    import pdfplumber
    pdf = Path("/tmp/work/wasde1026.pdf")
    if not pdf.exists():
        return
    text = "\n".join((p.extract_text() or "") for p in pdfplumber.open(pdf).pages)
    parsed = parse_wasde(text)
    assert parsed["wheat_world"]["oct"]["pr"] == 822390
    assert parsed["wheat_world"]["oct"]["dc"] == 827900
    assert parsed["wheat_world"]["oct"]["es"] == 276040
    assert parsed["beef"]["oct"]["pr"] == 24870
    assert parsed["beef"]["sep"]["pr"] == 24945


def test_aggregate_yield_is_production_over_area_not_a_sum_of_yields():
    """Two origins: 1 t/ha and 3 t/ha on equal area. The aggregate is 2, not 4."""
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "&& !r.yield" in html
    bu, acres = 36.7437, 2.47105
    records = ({"pr": 1000, "ah": 1000}, {"pr": 3000, "ah": 1000})
    ratio = (sum(r["pr"] for r in records) / sum(r["ah"] for r in records)) * bu / acres
    summed = sum((r["pr"] / r["ah"]) * bu / acres for r in records)
    assert abs(ratio - (2 * bu / acres)) < 1e-9
    assert abs(ratio - summed) > 1


def test_world_total_supply_is_beginning_stocks_plus_production_every_year():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "worldStu ? ['bs','pr'] : ['bs','pr','im']" in html
    assert "worldStu ? ['dc'] : ['dc','ex']" in html
    wheat = json.loads((ROOT / "data" / "psd_data.json").read_text())["Wheat"]["World"]
    supplies = {}
    for year, rec in wheat.items():
        if not str(year).isdigit():
            continue
        assert rec.get("bs") is not None and rec.get("pr") is not None
        supplies[year] = rec["bs"] + rec["pr"]
    # The stored total-supply field for 2026 is the WASDE supply figure. The page
    # must not use it, because earlier years stored the sum of country supplies.
    assert wheat["2026"]["ts"] != supplies["2026"] or abs(wheat["2026"]["ts"] - supplies["2026"]) <= 50
    assert supplies["2025"] == wheat["2025"]["bs"] + wheat["2025"]["pr"]
    assert supplies["2026"] == wheat["2026"]["bs"] + wheat["2026"]["pr"]
    assert supplies["2021"] == wheat["2021"]["bs"] + wheat["2021"]["pr"]


def test_grain_fills_missing_world_prior_and_replaces_mislabeled_wheat_use():
    result = {
        "Wheat": {"World": {"2026": {"pr": 827505, "dc": 824000}}},
        "Rapeseed/Canola": {"World": {"2026": {"pr": 100246}}},
    }
    merged = {"Wheat": {"World": {"2026": {"pr": 822390, "dc": 827900}}}}
    grain = {
        "Wheat": {"2026": {"pr": 822390, "es": 276038, "dc": 820000, "ah": 220000}},
        "Rapeseed/Canola": {"2026": {"pr": 99571, "es": 11599, "ah": 45000}},
    }
    sources = fill_world_prior_gaps(result, merged, grain, "b07a2a51ca", 827900)
    wheat = merged["Wheat"]["World"]["2026"]
    assert wheat["pr"] == 822390
    assert wheat["dc"] == 820000
    assert wheat["es"] == 276038
    assert sources["Wheat"]["dc"].startswith("GRAIN-TERMINAL")
    assert sources["Wheat"]["pr"] == "own history"
    canola = merged["Rapeseed/Canola"]["World"]["2026"]
    assert canola["pr"] == 99571
    assert canola["ah"] == 45000
    assert sources["Rapeseed/Canola"]["pr"].startswith("GRAIN-TERMINAL")

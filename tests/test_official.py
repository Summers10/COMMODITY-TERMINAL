"""Locks published figures the terminal must not recompute."""
import json
from pathlib import Path

from scripts.fetch_cattle import parse_cof, parse_inventory
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
    assert ng["value"] == 3801
    assert ng["avg5"] == 3747
    assert ng["vs_avg5_pct"] == 1.4
    assert ng["change"] == 77
    crude = next(s for s in energy["series"] if s["key"] == "crude_stocks")
    assert crude["value"] == 409.76
    assert crude["avg5"] is None
    assert crude["change"] == -0.865


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

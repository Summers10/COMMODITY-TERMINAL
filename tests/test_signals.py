"""The summary signals have to come back out of their own inputs."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_builder():
    spec = importlib.util.spec_from_file_location("build_signals", ROOT / "scripts" / "build_signals.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_saved_signals_match_a_fresh_build():
    module = load_builder()
    fresh = module.build()
    saved = json.loads((ROOT / "data" / "signals.json").read_text())
    assert fresh["sections"] == saved["sections"]
    assert fresh["rules"] == saved["rules"]
    assert fresh["config"] == saved["config"]


def test_each_signal_replays_and_there_is_no_row_total():
    module = load_builder()
    cfg = module.load_config()
    doc = json.loads((ROOT / "data" / "signals.json").read_text())
    rules = " ".join(rule["text"] for rule in doc["rules"])
    assert "pale amber" not in rules
    assert "Neutral has no colour" in rules
    assert "no row total" in rules
    grains = next(s for s in doc["sections"] if s["id"] == "grains")
    oilseeds = next(s for s in doc["sections"] if s["id"] == "oilseeds")
    assert [r["label"] for r in grains["rows"]] == [
        "Corn", "Wheat (Chicago SRW)", "Wheat (KC HRW)", "Wheat (MGEX)",
    ]
    assert [r["label"] for r in oilseeds["rows"]][0] == "Soybeans"
    assert "Soybeans" not in [r["label"] for r in grains["rows"]]
    assert "verdict" not in rules.lower()
    for section in doc["sections"]:
        assert "score" not in section
        assert section["groups"]
        for item in section["rows"]:
            assert "score" not in item
            assert "fund" not in item
            assert "mm" not in item
            for sig in item["signals"].values():
                if sig["state"]:
                    assert module.rescore(sig["rule_id"], sig["inputs"], cfg) == sig["state"]
                    assert sig["text"]
                    for word in ("Bullish", "Bearish", "Neutral"):
                        assert word not in sig["text"]
                else:
                    assert sig["text"] is None
            seasonal = item["signals"].get("seasonal")
            if seasonal and seasonal["state"]:
                weeks = seasonal["inputs"]["weeks"]
                assert len(weeks) == 5
                assert abs(sum(w["score"] for w in weeks) / 5 - seasonal["inputs"]["average"]) < 1e-6
                assert "Peak Trading Research seasonal, last reviewed" in seasonal["detail"]


def test_a_stale_input_becomes_a_dash():
    module = load_builder()
    cfg = module.load_config()
    stale = module.cell("bullish", "mm_flow", "2020-01-01", {"change_1w": 10, "change_4w": 20}, "old", "cftc", cfg)
    assert stale["state"] is None
    assert "stale" in stale["reason"]


def test_late_december_seasonal_wraps_into_january():
    module = load_builder()
    weeks = module.load_seasonals()["weeks"]
    labels = module.seasonal_week_labels(weeks, module.date(2026, 12, 28))
    assert labels == ["Dec 28", "Dec 29", "Jan 05", "Jan 12", "Jan 19"]


def test_seasonal_scores_do_not_expire():
    module = load_builder()
    cfg = module.load_config()
    assert "seasonal" not in cfg["cadence_days"]
    kept = module.cell("neutral", "seasonal", "2020-01-01", {"average": 0.4}, "kept", None, cfg)
    assert kept["state"] == "neutral"
    assert kept["text"]


def test_thresholds_are_the_config_file():
    cfg = json.loads((ROOT / "config" / "signals.json").read_text())
    assert cfg["stu_bull_pct"] == 33
    assert cfg["stu_bear_pct"] == 67
    assert cfg["mm_ext_long_pct"] == 85
    assert cfg["mm_ext_short_pct"] == 15
    assert cfg["energy_vs_avg_pct"] == 3
    assert cfg["cattle_yoy_low"] == 98
    assert cfg["cattle_yoy_high"] == 102
    assert cfg["seasonal_score_bull"] == 1
    assert cfg["seasonal_score_bear"] == -1
    assert cfg["neutral_fill"] is False
    assert "score_supportive" not in cfg
    assert "score_bearish" not in cfg


def test_world_softs_stocks_to_use_is_ending_over_domestic():
    """World stocks/use is ending stocks divided by domestic use, not by use plus exports.

    The World row is the USDA PSD world aggregate. The percentile is that ratio
    against the prior ten marketing years, and the current year is not in the sample.
    """
    psd = json.loads((ROOT / "data" / "psd_data.json").read_text())
    signals = json.loads((ROOT / "data" / "signals.json").read_text())
    softs = next(s for s in signals["sections"] if s["id"] == "softs")
    module = load_builder()
    for label, comm in (("Coffee", "Coffee"), ("Sugar", "Sugar"), ("Cotton", "Cotton")):
        world = psd[comm]["World"]
        years = sorted(int(y) for y in world if str(y).isdigit())
        series = []
        for year in years:
            row = world[str(year)]
            domestic = row["dc"]
            ending = row["es"]
            assert domestic and ending is not None
            # Exports are recorded, and they are not part of the world denominator.
            assert row.get("ex") is not None
            series.append((year, 100.0 * ending / domestic))
        current_year, current = series[-1]
        history = [v for _, v in series[-(11):-1]]
        assert len(history) == 10
        pct = module.percentile_at_or_below(current, history)
        cell = next(r for r in softs["rows"] if r["label"] == label)["signals"]["stu"]
        assert cell["inputs"]["stu"] == round(current, 4)
        assert cell["inputs"]["history"] == [round(v, 4) for v in history]
        assert cell["inputs"]["percentile"] == round(pct, 4)
        assert cell["inputs"]["ending_stocks"] == world[str(current_year)]["es"]

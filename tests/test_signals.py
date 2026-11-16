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


def test_each_signal_replays_from_its_inputs_and_the_tally_matches():
    module = load_builder()
    cfg = module.load_config()
    doc = json.loads((ROOT / "data" / "signals.json").read_text())
    for section in doc["sections"]:
        for item in section["rows"]:
            counts = {"bullish": 0, "bearish": 0, "neutral": 0}
            for sig in item["signals"].values():
                if sig["state"] in counts:
                    counts[sig["state"]] += 1
                    assert module.rescore(sig["rule_id"], sig["inputs"], cfg) == sig["state"]
            assert counts == item["tally"]


def test_a_stale_input_becomes_a_dash():
    module = load_builder()
    cfg = module.load_config()
    stale = module.cell("bullish", "mm_flow", "2020-01-01", {"change_1w": 10, "change_4w": 20}, "old", "cftc", cfg)
    assert stale["state"] is None
    assert "stale" in stale["reason"]


def test_thresholds_are_the_config_file():
    cfg = json.loads((ROOT / "config" / "signals.json").read_text())
    assert cfg["stu_bull_pct"] == 33
    assert cfg["stu_bear_pct"] == 67
    assert cfg["mm_ext_long_pct"] == 85
    assert cfg["mm_ext_short_pct"] == 15
    assert cfg["energy_vs_avg_pct"] == 3
    assert cfg["cattle_yoy_low"] == 98
    assert cfg["cattle_yoy_high"] == 102

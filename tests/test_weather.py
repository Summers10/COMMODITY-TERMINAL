"""Parsers for the weather glance. No network."""
from datetime import date

from scripts.fetch_weather import (
    REGIONS,
    parse_enso_status,
    parse_nino_week,
    parse_usdm_csv,
    pct_of_normal,
)


def test_thirty_research_stations_come_first():
    assert len(REGIONS) == 30
    assert REGIONS[0][1] == "Saskatoon, SK"
    assert REGIONS[3][1] == "Red Deer, AB"
    assert REGIONS[-1][1] == "Dubbo, NSW"
    labels = [r[1] for r in REGIONS]
    assert len(labels) == len(set(labels))
    for banned in ("Varginha, MG", "Ribeirão Preto, SP", "Daloa, CI"):
        assert banned not in labels
    assert {r[0] for r in REGIONS}.isdisjoint({"Coffee", "Sugar", "Cocoa"})


def test_nino_week_reads_the_latest_anomaly():
    text = """
                Nino1+2      Nino3        Nino34        Nino4
 Week          SST SSTA     SST SSTA     SST SSTA     SST SSTA
 02SEP1981     20.6-0.1     24.8-0.1     26.5-0.2     28.3-0.3
 11NOV2026     27.1 5.4     29.4 4.3     29.9 3.2     29.9 1.3
"""
    assert parse_nino_week(text) == ("2026-11-11", 3.2)


def test_enso_status_is_the_alert_line():
    page = "<p>ENSO Alert System Status: El Niño Advisory &nbsp; Synopsis: something</p>"
    assert parse_enso_status(page) == "El Niño Advisory"


def test_usdm_d1_is_the_cumulative_percent_and_the_weekly_change():
    text = (
        "MapDate,StateAbbreviation,None,D0,D1,D2,D3,D4,ValidStart,ValidEnd,StatisticFormatID\n"
        "20261117,ND,40,60,22.5,10,1,0,2026-11-17,2026-11-23,1\n"
        "20261110,ND,42,58,25.0,11,1,0,2026-11-10,2026-11-16,1\n"
    )
    got = parse_usdm_csv(text)
    assert got["code"] == "ND"
    assert got["d1_pct"] == 22.5
    assert got["change"] == -2.5
    assert got["week"] == "2026-11-17"


def test_percent_of_normal_does_not_invent_a_value():
    assert pct_of_normal(None, 10) is None
    assert pct_of_normal(10, 0) is None
    assert pct_of_normal(15, 10) == 150

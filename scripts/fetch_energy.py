#!/usr/bin/env python3
"""EIA weekly stocks. Levels and 5-year comparisons are the published ones.

Petroleum 5-year averages are not in WPSR Table 1 or Table 4. They are left
null rather than recomputed from the history. Natural gas uses the WNGSR
published 5-year average and the published percent change (the figure EIA
prints, including 3,747 Bcf when that is the published average).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import sys
import urllib.request

import xlrd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "energy.json")

TABLE1 = "https://ir.eia.gov/wpsr/table1.csv"
TABLE4 = "https://ir.eia.gov/wpsr/table4.csv"
PSW04 = "https://ir.eia.gov/wpsr/psw04.xls"
WNGSR = "https://ir.eia.gov/ngs/wngsr.json"
NG_HIST = "https://ir.eia.gov/ngs/ngshistory.xls"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return resp.read()


def fnum(raw):
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if s in ("", "–", "-", "NA"):
        return None
    return float(s)


def rows_csv(blob):
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("cp1252")
    return list(csv.reader(io.StringIO(text)))


def find_row(rows, label):
    for r in rows:
        if r and r[0].strip() == label:
            return r
    return None


def _check_change(label, value, week_ago, change):
    if None in (value, week_ago, change):
        raise ValueError(f"blank published cell in {label!r}")
    if abs((value - week_ago) - change) > 0.002:
        raise ValueError(f"{label} week change {change} does not match {value} minus {week_ago}")


def petroleum_from_table1(row):
    """Table 1: current, week ago, difference, week pct, year ago, difference, year pct."""
    if row is None or len(row) < 8:
        raise ValueError("WPSR Table 1 row missing published columns")
    value, week_ago, change = fnum(row[1]), fnum(row[2]), fnum(row[3])
    year_ago, yoy, yoy_pct = fnum(row[5]), fnum(row[6]), fnum(row[7])
    _check_change(row[0], value, week_ago, change)
    if None in (year_ago, yoy, yoy_pct):
        raise ValueError(f"blank year-ago cell in {row[0]!r}")
    return {
        "value": value, "week_ago": week_ago, "change": change,
        "year_ago": year_ago, "year_ago_change": yoy, "year_ago_pct": yoy_pct,
        "avg5": None, "vs_avg5": None, "vs_avg5_pct": None, "decimals": 3,
    }


def petroleum_from_table4(row):
    """Table 4: current, week ago, difference, year ago, year pct, two-years ago, pct."""
    if row is None or len(row) < 6:
        raise ValueError("WPSR Table 4 row missing published columns")
    value, week_ago, change = fnum(row[1]), fnum(row[2]), fnum(row[3])
    year_ago, yoy_pct = fnum(row[4]), fnum(row[5])
    _check_change(row[0], value, week_ago, change)
    if None in (year_ago, yoy_pct):
        raise ValueError(f"blank year-ago cell in {row[0]!r}")
    return {
        "value": value, "week_ago": week_ago, "change": change,
        "year_ago": year_ago, "year_ago_change": None, "year_ago_pct": yoy_pct,
        "avg5": None, "vs_avg5": None, "vs_avg5_pct": None, "decimals": 3,
    }


def history_from_psw(blob):
    book = xlrd.open_workbook(file_contents=blob)
    sh = book.sheet_by_name("Data 1")
    keys = [sh.cell_value(1, c) for c in range(sh.ncols)]
    want = {
        "WCESTUS1": "crude_stocks",
        "W_EPC0_SAX_YCUOK_MBBL": "cushing",
        "WGTSTUS1": "gas_stocks",
        "WDISTUS1": "dist_stocks",
    }
    cols = {want[k]: keys.index(k) for k in want}
    out = {k: [] for k in want.values()}
    for r in range(3, sh.nrows):
        serial = sh.cell_value(r, 0)
        if not isinstance(serial, (int, float)) or serial < 20000:
            continue
        day = xlrd.xldate_as_datetime(serial, book.datemode).date().isoformat()
        for key, col in cols.items():
            v = sh.cell_value(r, col)
            if isinstance(v, (int, float)) and v != "":
                out[key].append([day, round(v / 1000.0, 3)])
    for key, series in out.items():
        if len(series) < 200:
            raise ValueError(f"psw04 history for {key} is too short ({len(series)})")
    return out


def ng_from_json(blob):
    try:
        text = blob.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = blob.decode("cp1252")
    data = json.loads(text)
    series = next(s for s in data["series"] if s.get("name") == "total lower 48 states")
    calc = series["calculated"]
    points = {p[0]: p[1] for p in series["data"]}
    current = data["current_week"]
    week_ago = data["week_ago"]
    year_ago = data["year_ago"]
    value = points[current]
    prev = points[week_ago]
    ya = points[year_ago]
    change = calc["net_change"]
    avg5 = calc["5yr-avg"]
    pct = calc["pct-chg_5yr-avg"]
    yoy_pct = calc["pct-change_yrago"]
    if not isinstance(avg5, int) or not isinstance(value, int):
        raise ValueError("WNGSR stocks or 5-year average was not an integer as published")
    if change != value - prev:
        raise ValueError(f"WNGSR net change {change} != {value} - {prev}")
    return {
        "period": current,
        "release": str(data.get("release_date") or "")[:10],
        "week_ago_period": week_ago,
        "value": value, "week_ago": prev, "change": change,
        "year_ago": ya, "year_ago_change": value - ya, "year_ago_pct": yoy_pct,
        "avg5": avg5, "vs_avg5": value - avg5, "vs_avg5_pct": pct,
        "avg5_label": data.get("5yr_avg"),
        "decimals": 0,
    }


def ng_history(blob):
    """Weekly working-gas stocks only. The 5-year average is not in this file."""
    book = xlrd.open_workbook(file_contents=blob)
    sh = book.sheet_by_index(0)
    out = []
    for r in range(sh.nrows):
        row = [sh.cell_value(r, c) for c in range(min(3, sh.ncols))]
        # Accept a date in col 0 and a number in col 1.
        d = row[0]
        if isinstance(d, (int, float)) and d > 20000:
            day = xlrd.xldate_as_datetime(d, book.datemode).date()
            if isinstance(row[1], (int, float)):
                out.append([day.isoformat(), int(round(row[1]))])
        elif isinstance(d, str) and len(d) >= 8 and d[:4].isdigit():
            try:
                day = dt.date.fromisoformat(d[:10])
            except ValueError:
                continue
            if isinstance(row[1], (int, float)):
                out.append([day.isoformat(), int(round(row[1]))])
    return out[-400:]


def main():
    previous = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            previous = {s["key"]: s for s in json.load(f).get("series", [])}
    failures = []
    try:
        t1 = rows_csv(get(TABLE1))
        t4 = rows_csv(get(TABLE4))
        hist = history_from_psw(get(PSW04))
        period = None
        # Table 1 header is the week ending, second column.
        header = t1[0]
        period = header[1]
        period_iso = dt.datetime.strptime(period, "%m/%d/%y").date().isoformat()
        specs = [
            ("crude_stocks", "Crude (ex-SPR)", "million barrels", petroleum_from_table1(find_row(t1, "Commercial (Excluding SPR)")), "WPSR Table 1", TABLE1),
            ("gas_stocks", "Gasoline", "million barrels", petroleum_from_table1(find_row(t1, "Total Motor Gasoline")), "WPSR Table 1", TABLE1),
            ("dist_stocks", "Distillate", "million barrels", petroleum_from_table1(find_row(t1, "Distillate Fuel Oil")), "WPSR Table 1", TABLE1),
            ("cushing", "Crude (Cushing)", "million barrels", petroleum_from_table4(find_row(t4, "Cushing")), "WPSR Table 4", TABLE4),
        ]
        series = []
        for key, label, unit, rec, table, url in specs:
            last = hist[key][-1]
            if last[0] != period_iso or abs(last[1] - rec["value"]) > 0.001:
                raise ValueError(f"{key} history {last} != published {period_iso} {rec['value']}")
            # Cushing's table4 row has a shorter header. Year-ago percent column differs.
            series.append({
                "key": key, "label": label, "unit": unit, "period": period_iso,
                "source": table, "source_url": url, "ok": True, "error": None,
                "history": hist[key][-520:], "forward": [],
                **rec,
            })
        ng_blob = get(WNGSR)
        ng = ng_from_json(ng_blob)
        try:
            ngh = ng_history(get(NG_HIST))
        except Exception as e:
            ngh = []
            print(f"NG history file not used ({e})", file=sys.stderr)
        if ngh and ngh[-1][0] == ng["period"] and ngh[-1][1] != ng["value"]:
            raise ValueError(f"NG history {ngh[-1]} != WNGSR {ng['value']}")
        series.append({
            "key": "ng_storage", "label": "Natural gas (Lower 48)", "unit": "Bcf",
            "source": "WNGSR", "source_url": "https://ir.eia.gov/ngs/wngsr.html",
            "ok": True, "error": None, "history": ngh, "forward": [],
            **ng,
        })
    except Exception as e:
        failures.append(str(e))
        print(f"FAIL energy {e}", file=sys.stderr)
        if not previous:
            sys.exit(1)
        series = list(previous.values())
        for s in series:
            s["ok"] = False
            s["error"] = failures[0]

    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    for s in series:
        s["checked_at"] = now
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump({
            "generated_at": now,
            "source": "U.S. Energy Information Administration",
            "note": "5-year average is the WNGSR published figure. WPSR tables used here do not print a 5-year average, so those cells are null.",
            "series": series,
        }, f, indent=1)
        f.write("\n")
    os.replace(tmp, OUT)
    for s in series:
        if s.get("ok"):
            print(f"OK {s['key']:14} {s.get('period')} {s.get('value')} avg5={s.get('avg5')}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

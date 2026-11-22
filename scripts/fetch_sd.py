#!/usr/bin/env python3
"""Canada canola supply and disposition.

StatsCan 32-10-0013 is the final crop-year balance. StatsCan 32-10-0359 is
harvested area and yield. AAFC's monthly Canada Outlook supplies the years
StatsCan has not finalised, plus the previous report for the prior column.
A sheet that does not balance is not published.
"""
import csv
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(__file__))
from fetch_cgc import _get  # noqa: E402

OUT = os.environ.get("SD_OUT", os.path.join(os.path.dirname(__file__), "..", "data", "sd.json"))
ARCHIVE = os.path.join(os.path.dirname(OUT), "aafc")

SC_SD = "https://www150.statcan.gc.ca/n1/tbl/csv/32100013-eng.zip"
SC_AYP = "https://www150.statcan.gc.ca/n1/tbl/csv/32100359-eng.zip"
AAFC_BASE = "https://agriculture.canada.ca"
AAFC_LIST = AAFC_BASE + "/en/sector/crops/reports-statistics"

CROP = {
    "sd": "Canola",
    "ayp": "Canola (rapeseed)",
    "aafc": r"^canola",
    "lb_bu": 50.0,
}
HA_TO_AC = 2.471053814
TOL = 3.0


def fetch(url):
    code, raw = _get(url)
    if code != 200 or not raw:
        raise RuntimeError(f"download failed ({code}): {url}")
    return raw


def fetch_zip(url):
    """StatsCan sometimes answers 200 with an HTML page. Retry until the body is a zip."""
    last = None
    for attempt in range(1, 5):
        code, raw = _get(url)
        if code == 200 and raw[:2] == b"PK":
            return raw
        last = (code, len(raw or b""))
        print(f"    not a zip (HTTP {code}, {len(raw or b'')} bytes), retry {attempt}", flush=True)
        time.sleep(8 * attempt)
    raise RuntimeError(f"download was not a zip after retries ({last}): {url}")


def cy_label(start):
    return f"{start}-{start + 1}"


def statcan_rows(blob, crop_name, crop_col):
    z = zipfile.ZipFile(io.BytesIO(blob))
    name = next(n for n in z.namelist() if not n.lower().endswith("_metadata.csv"))
    with z.open(name) as f:
        rdr = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig"))
        hdr = next(rdr)
        ix = {h: i for i, h in enumerate(hdr)}
        ci = ix[crop_col]
        for r in rdr:
            if len(r) < len(hdr) or r[ix["GEO"]] != "Canada" or r[ci] != crop_name:
                continue
            yield r, ix


def parse_statcan_sd(blob):
    years = {}
    for r, ix in statcan_rows(blob, CROP["sd"], "Type of crop"):
        ref = r[ix["REF_DATE"]]
        if not ref.endswith("-07"):
            continue
        v = r[ix["VALUE"]].strip()
        if v == "":
            continue
        cy = cy_label(int(ref[:4]) - 1)
        years.setdefault(cy, {})[r[ix["Supply and disposition of grains"]]] = float(v)
    out = {}
    for cy, d in years.items():
        def g(n, d=d):
            return d.get(n, 0.0)
        fi = g("Human food") + g("Industrial use")
        fwd = g("Animal feed, waste and dockage")
        dom = g("Total domestic disappearance")
        out[cy] = {
            "beg": g("Total beginning stocks"),
            "prod": g("Production"),
            "imp": g("Imports"),
            "supply": g("Total supplies"),
            "exp": g("Total exports"),
            "fi": fi,
            "fwd": fwd,
            "seed_other": dom - fi - fwd,
            "dom": dom,
            "end": g("Total ending stocks"),
            "src": "StatsCan",
        }
    return out


def parse_statcan_ayp(blob):
    keep = {
        "Harvested area (acres)": "ac_harv",
        "Average yield (bushels per acre)": "bu_ac",
    }
    out = {}
    for r, ix in statcan_rows(blob, CROP["ayp"], "Type of crop"):
        metric = keep.get(r[ix["Harvest disposition"]])
        v = r[ix["VALUE"]].strip()
        if not metric or v == "":
            continue
        cy = cy_label(int(r[ix["REF_DATE"]][:4]))
        slot = out.setdefault(cy, {})
        slot[metric] = float(v) / 1000.0 if metric.startswith("ac_") else float(v)
    return out


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self._t = None
        self._row = None
        self._cell = None
        self._in_cap = False
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._t = {"caption": "", "rows": [], "foot": False}
        elif self._t is None:
            return
        elif tag == "caption":
            self._in_cap = True
        elif tag == "tfoot":
            self._t["foot"] = True
        elif tag == "tr" and not self._t["foot"]:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = ""
        elif tag == "sup":
            self._skip += 1
        elif tag == "span" and ("class", "wb-inv") in attrs:
            self._skip += 1

    def handle_endtag(self, tag):
        if self._t is None:
            return
        if tag == "table":
            self.tables.append(self._t)
            self._t = None
        elif tag == "caption":
            self._in_cap = False
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join(self._cell.split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self._t["rows"].append(self._row)
            self._row = None
        elif tag in ("sup", "span") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._t is None or self._skip:
            return
        if self._in_cap:
            self._t["caption"] += data
        elif self._cell is not None:
            self._cell += data


AAFC_ROWS = [
    (r"^area harvested", "ha_harv"),
    (r"^yield", "t_ha"),
    (r"^production", "prod"),
    (r"^imports", "imp"),
    (r"^total supply", "supply"),
    (r"^exports", "exp"),
    (r"^food and industrial", "fi"),
    (r"^feed, waste", "fwd"),
    (r"^total domestic use", "dom"),
    (r"^carry-out stocks", "end"),
    (r"^average price", "price"),
]


def num(s):
    s = s.replace(",", "").replace("\u00a0", "").strip()
    return float(s) if re.fullmatch(r"-?\d+(\.\d+)?", s) else None


def parse_aafc(html):
    parser = TableParser()
    parser.feed(html)
    table = next(
        (t for t in parser.tables if re.search(CROP["aafc"], " ".join(t["caption"].split()), re.I)),
        None,
    )
    if not table:
        raise ValueError("AAFC canola table not found")
    years = [m.group(0) for h in table["rows"][0] if (m := re.match(r"(\d{4})-(\d{4})", h))]
    if len(years) < 2:
        raise ValueError(f"AAFC canola crop-year header not found: {table['rows'][0]}")
    cols = {cy: {} for cy in years}
    for row in table["rows"][1:]:
        label = row[0].lower()
        key = next((k for pat, k in AAFC_ROWS if re.search(pat, label)), None)
        if not key:
            continue
        for cy, raw in zip(years, row[-len(years):]):
            cols[cy][key] = num(raw)
    for cy, d in cols.items():
        missing = [k for k in ("prod", "imp", "supply", "exp", "dom", "end") if d.get(k) is None]
        if missing:
            raise ValueError(f"AAFC canola {cy}: rows missing {missing}")
        d["beg"] = d["supply"] - d["prod"] - d["imp"]
        d["seed_other"] = d["dom"] - (d.get("fi") or 0) - (d.get("fwd") or 0)
        d["src"] = "AAFC"
    dated = re.search(r"Outlook for Principal Field Crops,?\s*(\d{4}-\d{2}-\d{2})", html)
    return cols, (dated.group(1) if dated else None)


def aafc_report_urls():
    html = fetch(AAFC_LIST).decode("utf-8", "replace")
    links = re.findall(
        r'href="([^"]+)"[^>]*>[^<]*((?:20\d{2}-\d{2}-\d{2}))[^<]*</a>',
        html,
        re.I,
    )
    # The current edition's href is a stable path; the date is in the link text.
    links = [
        (href, day) for href, day in links
        if "outlook" in href.lower() and "principal" in href.lower()
    ]
    seen, out = set(), []
    for href, day in sorted(links, key=lambda x: x[1], reverse=True):
        if day in seen:
            continue
        seen.add(day)
        out.append((day, href if href.startswith("http") else AAFC_BASE + href))
    if not out:
        raise RuntimeError("no AAFC outlook links on the reports page")
    return out


def check_sheet(tag, sheet, errs):
    supply = sheet["beg"] + sheet["prod"] + sheet["imp"]
    use = sheet["exp"] + sheet["dom"] + sheet["end"]
    if abs(supply - sheet["supply"]) > TOL:
        errs.append(f"{tag}: beg+prod+imp {supply:.0f} != supply {sheet['supply']:.0f}")
    if abs(use - sheet["supply"]) > TOL:
        errs.append(f"{tag}: exp+dom+end {use:.0f} != supply {sheet['supply']:.0f}")
    for key in ("prod", "supply", "exp", "dom", "end"):
        if sheet.get(key) is None or sheet[key] < 0:
            errs.append(f"{tag}: bad {key}={sheet.get(key)}")


def build(sd, ayp, latest, latest_date, latest_url, prior, prior_date):
    errs, warns = [], []
    years = {}
    for cy, sheet in sd.items():
        check_sheet(f"StatsCan canola {cy}", sheet, errs)
        years[cy] = dict(sheet)
    aafc_years = sorted(latest)
    forecast = aafc_years[-1]
    for cy in aafc_years:
        sheet = latest[cy]
        check_sheet(f"AAFC {latest_date} canola {cy}", sheet, errs)
        if cy in years:
            final = years[cy]
            for key in ("prod", "exp", "end"):
                if abs(final[key] - sheet[key]) > max(TOL, 0.005 * final[key]):
                    warns.append(
                        f"canola {cy} {key}: StatsCan {final[key]:.0f} vs AAFC {sheet[key]:.0f}"
                    )
            years[cy]["price"] = sheet.get("price")
        else:
            years[cy] = dict(sheet)
    for cy, sheet in years.items():
        area = ayp.get(cy)
        if area and "ac_harv" in area:
            sheet["ac_harv"] = area["ac_harv"]
            sheet["bu_ac"] = area.get("bu_ac")
        elif sheet.get("ha_harv"):
            sheet["ac_harv"] = sheet["ha_harv"] * HA_TO_AC
            if sheet.get("t_ha"):
                sheet["bu_ac"] = sheet["t_ha"] * 2204.62262 / CROP["lb_bu"] / HA_TO_AC
        sheet["total_use"] = sheet["exp"] + sheet["dom"]
        sheet["su"] = sheet["end"] / sheet["total_use"] * 100 if sheet["total_use"] else None
    prior_fc = None
    if prior and forecast in prior:
        prev = dict(prior[forecast])
        prev["total_use"] = prev["exp"] + prev["dom"]
        prev["su"] = prev["end"] / prev["total_use"] * 100 if prev["total_use"] else None
        cur = years[forecast]
        if prev.get("ha_harv") and cur.get("ha_harv") and cur.get("ac_harv"):
            prev["ac_harv"] = cur["ac_harv"] * prev["ha_harv"] / cur["ha_harv"]
        if prev.get("t_ha") and cur.get("t_ha") and cur.get("bu_ac"):
            prev["bu_ac"] = cur["bu_ac"] * prev["t_ha"] / cur["t_ha"]
        prior_fc = prev
    elif prior:
        warns.append(f"prior AAFC report has no {forecast} column")
    return {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aafc": {
            "date": latest_date,
            "url": latest_url,
            "prior_date": prior_date,
            "source_url": "https://agriculture.canada.ca/en/sector/crops/reports-statistics",
        },
        "statcan": {
            "supply_disposition": SC_SD,
            "area_yield": SC_AYP,
            "latest": max(sd) if sd else None,
        },
        "crops": {
            "canola": {
                "years": dict(sorted(years.items())),
                "forecast_year": forecast,
                "aafc_years": aafc_years,
                "prior": prior_fc,
            }
        },
        "checks": {"notes": warns},
    }, errs, warns


def main():
    sd = parse_statcan_sd(fetch_zip(SC_SD))
    ayp = parse_statcan_ayp(fetch_zip(SC_AYP))
    reports = aafc_report_urls()
    latest_date, latest_url = reports[0]
    latest, _ = parse_aafc(fetch(latest_url).decode("utf-8", "replace"))
    prior, prior_date = None, None
    if len(reports) > 1:
        prior_date, prior_url = reports[1]
        try:
            prior, _ = parse_aafc(fetch(prior_url).decode("utf-8", "replace"))
        except Exception as exc:  # noqa: BLE001
            print(f"  note: prior AAFC report unreadable: {exc}")
    print(f"  StatsCan canola {min(sd)}..{max(sd)}; AAFC latest {latest_date}, prior {prior_date}")
    doc, errs, warns = build(sd, ayp, latest, latest_date, latest_url, prior, prior_date)
    for note in warns:
        print("  note: " + note)
    if errs:
        print("\nS&D VALIDATION FAILED - not publishing:", file=sys.stderr)
        for err in errs:
            print("  - " + err, file=sys.stderr)
        sys.exit(1)
    os.makedirs(ARCHIVE, exist_ok=True)
    with open(os.path.join(ARCHIVE, f"{latest_date}.json"), "w") as f:
        json.dump(latest, f, separators=(",", ":"))
        f.write("\n")
    with open(OUT, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
        f.write("\n")
    print(f"Wrote {OUT}: AAFC {latest_date}, {len(doc['crops']['canola']['years'])} crop years")


if __name__ == "__main__":
    main()

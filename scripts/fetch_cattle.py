#!/usr/bin/env python3
"""Cattle supply, slaughter and prices from published USDA reports.

No CFTC series are written here. Live and feeder cattle positioning stays on
the CFTC page. A figure the report does not print is stored as null.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import urllib.request
from datetime import date

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "cattle.json")
UA = {"User-Agent": "Mozilla/5.0"}


def get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def num(raw):
    return float(str(raw).replace(",", ""))


# The February report adds the annual supplement, so the contents page lists a
# United States header before the data table. October 2025 was not released.
COF_NOT_RELEASED = {
    "2025-10-01": (
        "NASS cancelled the October 24, 2025 Cattle on Feed release during the appropriations lapse. "
        "It is not on the ESMIS Cattle on Feed release list."
    ),
}
HEADER_RE = re.compile(
    r"1,000\+ Capacity Feedlots - United States:\s+(\w+) 1, (\d{4}) and (\d{4})"
)
ROW_RE = re.compile(
    r"\s*(On feed \w+ 1|Placed on feed during \w+|Fed cattle marketed during \w+|Other disappearance during \w+)"
    r"\s*\.*:\s*([\d,]+)\s+([\d,]+)\s+(\d+)"
)


def parse_cof(text: str) -> dict:
    """The current U.S. 1,000+ capacity table. Percents are the printed ones.

    The header has to be the one sitting on the data rows. A contents line names
    the same kind of header and is not the table.
    """
    matches = list(HEADER_RE.finditer(text))
    header = None
    block = ""
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else match.end() + 1800
        candidate = text[match.end():end]
        month = match.group(1)
        if ROW_RE.search(candidate) and f"On feed {month} 1" in candidate:
            header = match
            block = candidate
            break
    if header is None:
        raise ValueError("Cattle on Feed U.S. table header not found")
    month, y1 = header.group(1), int(header.group(3))
    rows = {}
    for line in block.splitlines():
        m = re.match(
            r"\s*(On feed \w+ 1|Placed on feed during \w+|Fed cattle marketed during \w+|Other disappearance during \w+)\s*\.*:\s*([\d,]+)\s+([\d,]+)\s+(\d+)",
            line,
        )
        if not m:
            continue
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        rows[label] = {
            "year_ago": int(num(m.group(2))),
            "current": int(num(m.group(3))),
            "pct_of_year_ago": int(m.group(4)),
        }
    on_feed = rows.get(f"On feed {month} 1")
    placed = next((v for k, v in rows.items() if k.startswith("Placed")), None)
    marketed = next((v for k, v in rows.items() if k.startswith("Fed cattle marketed")), None)
    other = next((v for k, v in rows.items() if k.startswith("Other disappearance")), None)
    if not all((on_feed, placed, marketed, other)):
        raise ValueError(f"Cattle on Feed rows incomplete: {list(rows)}")
    months = {n: i for i, n in enumerate(
        ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
    asof = date(y1, months[month], 1).isoformat()
    released = re.search(r"Released (\w+ \d{1,2}, \d{4})", text)
    return {
        "as_of": asof,
        "released": released.group(1) if released else None,
        "on_feed": on_feed,
        "placements": placed,
        "marketings": marketed,
        "other_disappearance": other,
    }


def _esmis_text(year, month):
    """The Cornell copy, used when release.nass has no cofdMMYY.txt."""
    for day in range(15, 32):
        try:
            stamp = date(year, month, day).isoformat()
        except ValueError:
            continue
        page = f"https://usda.library.cornell.edu/publication/cattle-feed/{stamp}"
        try:
            html = get(page, timeout=20).decode("utf-8", "replace")
        except Exception:
            continue
        link = re.search(r'href="([^"]+cofd\d+\.txt)"', html)
        if not link:
            continue
        href = link.group(1)
        if href.startswith("/"):
            href = "https://usda.library.cornell.edu" + href
        return get(href, timeout=40).decode("latin-1", "replace"), href
    return None, None


def fetch_cof_month(year, month):
    """Text and URL for one release month. (None, None) when NASS did not publish it."""
    slug = f"cofd{month:02d}{year % 100:02d}.txt"
    nass = f"https://release.nass.usda.gov/reports/{slug}"
    try:
        text = get(nass, timeout=25).decode("latin-1", "replace")
        if "Cattle on Feed" in text and "1,000 head" in text:
            return text, nass
    except Exception:
        text = ""
    return _esmis_text(year, month)


def cof_history():
    """Monthly Cattle on Feed from January 2021 through the latest release.

    Returns (rows, gaps). A gap is a month NASS did not publish. Nothing is filled in.
    """
    today = date.today()
    out = []
    gaps = []
    year, month = 2021, 1
    while date(year, month, 1) <= today:
        as_of = f"{year:04d}-{month:02d}-01"
        text, url = fetch_cof_month(year, month)
        if text:
            try:
                row = parse_cof(text)
            except ValueError as e:
                print(f"  skip {as_of}: {e}", file=sys.stderr)
                row = None
            if row and row["as_of"] == as_of:
                row["source_url"] = url
                out.append(row)
            elif row:
                print(f"  skip {as_of}: file is the {row['as_of']} table", file=sys.stderr)
        elif as_of in COF_NOT_RELEASED:
            gaps.append({"as_of": as_of, "reason": COF_NOT_RELEASED[as_of]})
            print(f"  no release {as_of}", file=sys.stderr)
        elif date(year, month, 1) < date(today.year, today.month, 1):
            print(f"  missing {as_of}: no NASS or ESMIS file", file=sys.stderr)
        month += 1
        if month == 13:
            month = 1
            year += 1
    by_date = {}
    for row in out:
        by_date[row["as_of"]] = row
    rows = [by_date[k] for k in sorted(by_date)]
    if len(rows) < 12:
        raise ValueError(f"only {len(rows)} Cattle on Feed reports parsed")
    return rows, gaps


def parse_outside_feedlots(text: str):
    """The printed outside-feedlots total. None when the report does not state it.

    July says "is down 1 percent from the 33.8 million head".
    January says "was 1 percent above January 1". The percent is the one NASS prints.
    """
    flat = re.sub(r"\s+", " ", text)
    m = re.search(
        r"outside of feedlots\), at\s+([\d.]+) million head, is (up|down|unchanged)"
        r"(?:\s+(\d+)\s+percent)? from the ([\d.]+) million head",
        flat,
    )
    if m:
        current = float(m.group(1))
        direction, points, year_ago = m.group(2), m.group(3), float(m.group(4))
    else:
        m = re.search(
            r"outside of feedlots\), at\s+([\d.]+) million head, was (\d+) percent (above|below)",
            flat,
        )
        if not m:
            return None
        current = float(m.group(1))
        points = m.group(2)
        direction = "up" if m.group(3) == "above" else "down"
        year_ago = None
    if direction == "unchanged" or not points:
        pct = 100
    elif direction == "down":
        pct = 100 - int(points)
    else:
        pct = 100 + int(points)
    return {
        "current_million": current,
        "year_ago_million": year_ago,
        "pct_of_year_ago": pct,
        "printed": m.group(0),
    }


def parse_inventory(text: str) -> dict:
    header = re.search(
        r"Cattle Inventory by Class and Calf Crop - United States:\s+(\w+) 1, (\d{4}) and (\d{4})",
        text,
    )
    if not header:
        raise ValueError("cattle inventory table not found")
    month, y0, y1 = header.group(1), int(header.group(2)), int(header.group(3))
    # Prefer the data table over the contents line, which shares the title.
    starts = [m.start() for m in re.finditer(re.escape(header.group(0)[:40]), text)]
    start = header.start()
    block = text[start:start + 6000]
    want = {
        "All cattle and calves": "all_cattle",
        "Cattle and calves": "all_cattle",
        "Beef cows": "beef_cows",
        "For beef cow replacement": "heifers_retained",
        "Calf crop": "calf_crop",
    }
    found = {}
    for line in block.splitlines():
        m = re.match(r"\s*(.*?)\s*\.*:\s*([\d,.]+|\(NA\))\s+([\d,.]+)\s+(\d+|\(X\))", line)
        if not m:
            continue
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        key = want.get(label)
        if not key or key in found:
            continue
        ya = None if m.group(2) == "(NA)" else num(m.group(2))
        pct = None if m.group(4) == "(X)" else int(m.group(4))
        found[key] = {"year_ago": ya, "current": num(m.group(3)), "pct_of_year_ago": pct}
    missing = [k for k in want.values() if k not in found]
    if missing:
        raise ValueError(f"inventory missing {missing}")
    released = re.search(r"Released (\w+ \d{1,2}, \d{4})", text)
    return {
        "as_of": f"{y1}-{1 if month == 'January' else 7:02d}-01",
        "released": released.group(1) if released else None,
        "rows": found,
        "outside_feedlots": parse_outside_feedlots(text),
    }


def latest_inventory():
    reports = []
    today = date.today()
    for year in (today.year, today.year - 1):
        for mm in (1, 7):
            slug = f"catl{mm:02d}{year % 100:02d}.txt"
            url = f"https://release.nass.usda.gov/reports/{slug}"
            try:
                text = get(url).decode("latin-1", "replace")
            except Exception:
                continue
            if "Cattle Inventory by Class" not in text:
                continue
            try:
                row = parse_inventory(text)
            except ValueError as e:
                print(f"  skip {slug}: {e}", file=sys.stderr)
                continue
            row["source_url"] = url
            reports.append(row)
    if not reports:
        raise ValueError("no January/July cattle inventory report")
    # Keep the newest January and the newest July. Earlier releases are revised later.
    latest = {}
    for row in reports:
        key = row["as_of"][5:7]
        if key not in latest or row["as_of"] > latest[key]["as_of"]:
            latest[key] = row
    return [latest[k] for k in sorted(latest)]


def pdf_text(url):
    blob = get(url, timeout=60)
    if not blob.startswith(b"%PDF"):
        raise ValueError(f"{url} was not a PDF")
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def parse_slaughter(text: str) -> dict:
    period = re.search(r"Report for (\w+ \d{1,2}, \d{4}) thru (\w+ \d{1,2}, \d{4})", text)
    if not period:
        raise ValueError("slaughter report period not found")
    total = re.search(r"\nTotal\s+([\d,]+)\s+[\d,]+", text)
    if not total:
        raise ValueError("slaughter cattle total not found")
    dressed = re.search(r"Dressed Weight \(lbs\)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)", text)
    if not dressed:
        raise ValueError("dressed weights not found")
    # This report prints the week. It does not print a year-ago or a 5-year average.
    return {
        "week_start": period.group(1),
        "week_end": period.group(2),
        "cattle_head": int(num(total.group(1))),
        "dressed_lbs": {
            "cattle": int(num(dressed.group(1))),
            "steers": int(num(dressed.group(2))),
            "heifers": int(num(dressed.group(3))),
        },
        "year_ago_head": None,
        "avg5_head": None,
        "source_url": "https://www.ams.usda.gov/mnreports/ams_3658.pdf",
    }


def parse_steer(text: str) -> dict:
    week = re.search(r"Week Ending \w+, (\d{1,2}/\d{1,2}/\d{4})", text)
    if not week:
        raise ValueError("5-area week ending not found")
    def line(label, chunk):
        m = re.search(rf"{label}\s+([\d,]+)\s+([\d,]+)\s+([\d.]+)", chunk)
        if not m:
            raise ValueError(f"missing {label}")
        return {"head": int(num(m.group(1))), "avg_weight": int(num(m.group(2))), "price": num(m.group(3))}
    parts = re.split(r"SAME PERIOD LAST ", text)
    if len(parts) < 3:
        raise ValueError("5-area last-week / last-year blocks not found")
    current, last_week, last_year = parts[0], parts[1], parts[2]
    return {
        "week_ending": week.group(1),
        "live_fob_steer": line("Live FOB Steer", current),
        "live_fob_steer_week_ago": line("Live FOB Steer", last_week),
        "live_fob_steer_year_ago": line("Live FOB Steer", last_year),
        "dressed_steer": line("Dressed Del Steer", current),
        "source_url": "https://www.ams.usda.gov/mnreports/ams_2477.pdf",
        "note": "Negotiated 5-area weekly weighted average, live FOB steer, beef type, as printed.",
    }


def _money(raw: str) -> float:
    """AMS prints a decline in parentheses, for example (1.95)."""
    raw = raw.strip().replace(",", "")
    if raw.startswith("(") and raw.endswith(")"):
        return -float(raw[1:-1])
    return float(raw)


def parse_cutout(text: str) -> dict:
    dated = re.search(r"Agricultural Marketing Service\s+([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    vals = re.search(r"Current Cutout Values:\s+([\d.]+)\s+([\d.]+)", text)
    chg = re.search(r"Change from prior day:\s+(\(?[-+\d.]+\)?)\s+(\(?[-+\d.]+\)?)", text)
    if not (vals and chg):
        raise ValueError("boxed beef cutout values not found")
    return {
        "as_of": dated.group(1) if dated else None,
        "choice": num(vals.group(1)),
        "select": num(vals.group(2)),
        "choice_change": _money(chg.group(1)),
        "select_change": _money(chg.group(2)),
        "unit": "$/cwt",
        "source_url": "https://www.ams.usda.gov/mnreports/ams_2453.pdf",
    }


def wasde_beef():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fetch_psd import fetch_wasde_pdf_text
    from wasde_tables import parse_wasde
    text, url = fetch_wasde_pdf_text()
    parsed = parse_wasde(text)
    beef = parsed["beef"]
    return {
        "source_url": url,
        "wasde_number": parsed.get("wasde_number"),
        "dated": parsed.get("dated"),
        "unit": "million pounds",
        "beef_2025": beef["2025"],
        "beef_prior": beef["sep"],
        "beef_current": beef["oct"],
        "steer_price": parsed.get("steer_price"),
    }


def main():
    previous = {}
    if os.path.exists(OUT):
        with open(OUT) as f:
            previous = json.load(f)
    doc = {
        "source": "USDA NASS and USDA AMS",
        "updated": date.today().isoformat(),
    }
    errors = []

    def keep(key, fn):
        try:
            doc[key] = fn()
            print(f"OK {key}")
        except Exception as e:
            errors.append(f"{key}: {e}")
            print(f"FAIL {key}: {e}", file=sys.stderr)
            if key in previous:
                doc[key] = previous[key]
                doc[key + "_error"] = str(e)

    gaps = {}

    def load_on_feed():
        rows, missing = cof_history()
        gaps["rows"] = missing
        return rows

    keep("on_feed", load_on_feed)
    if "rows" in gaps:
        doc["on_feed_gaps"] = gaps["rows"]
    elif "on_feed_gaps" in previous:
        doc["on_feed_gaps"] = previous["on_feed_gaps"]
    keep("inventory", latest_inventory)
    keep("slaughter", lambda: parse_slaughter(pdf_text("https://www.ams.usda.gov/mnreports/ams_3658.pdf")))
    keep("steer", lambda: parse_steer(pdf_text("https://www.ams.usda.gov/mnreports/ams_2477.pdf")))
    keep("cutout", lambda: parse_cutout(pdf_text("https://www.ams.usda.gov/mnreports/ams_2453.pdf")))
    keep("wasde", wasde_beef)
    # CME Feeder Cattle Index is not on a keyless feed (the CME page returns 403).
    doc["feeder"] = None
    doc["feeder_note"] = "CME Feeder Cattle Index is not available on a keyless official feed. No substitute auction average is shown."

    if "on_feed" not in doc or "steer" not in doc or "cutout" not in doc:
        print("Refusing to publish cattle file without on-feed, steer and cutout.", file=sys.stderr)
        sys.exit(1)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f)
        f.write("\n")
    os.replace(tmp, OUT)
    print(f"Wrote {OUT} ({os.path.getsize(OUT):,} bytes)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

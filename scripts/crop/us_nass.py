"""United States – USDA NASS Crop Progress & Condition via the Quick Stats API.

Needs a free key: https://quickstats.nass.usda.gov/api  -> secret NASS_API_KEY
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from common import env, payload, rec, session, validate

API = "https://quickstats.nass.usda.gov/api/api_GET/"
SOURCE_URL = "https://www.nass.usda.gov/Publications/National_Crop_Progress/"
LIST_URL = "https://esmis.nal.usda.gov/publication/crop-progress"


def _published_text() -> str:
    s = session()
    page = s.get(LIST_URL, timeout=60)
    page.raise_for_status()
    hrefs = re.findall(r'href="([^"]+prog\d+\.txt)"', page.text)
    if not hrefs:
        raise RuntimeError("no crop progress text file on the NASS publication page")
    href = max(hrefs, key=lambda h: int(re.search(r"prog(\d+)", h).group(1)))
    if href.startswith("/"):
        href = "https://esmis.nal.usda.gov" + href
    body = s.get(href, timeout=60)
    body.raise_for_status()
    text = body.text
    if "Crop Progress" not in text:
        raise RuntimeError(f"crop progress download was not the report ({href})")
    return text

STAGE_MAP = {
    "PLANTED": "planted", "EMERGED": "emerged", "HARVESTED": "harvested",
    "SILKING": "silking", "DOUGH": "dough", "DENTED": "dented", "MATURE": "mature",
    "BLOOMING": "blooming", "SETTING PODS": "setting pods", "DROPPING LEAVES": "dropping leaves",
    "HEADED": "headed", "COLORING": "coloring", "SQUARING": "squaring",
    "SETTING BOLLS": "setting bolls", "BOLLS OPENING": "bolls opening",
    "JOINTED": "jointed", "BOOTED": "booted", "HEADED OUT": "headed",
}

CONDITION_UNITS = {"PCT EXCELLENT": "ex", "PCT GOOD": "gd", "PCT FAIR": "fr",
                   "PCT POOR": "pr", "PCT VERY POOR": "vp"}


def crop_label(short_desc: str) -> str:
    # "CORN, GRAIN - PROGRESS, MEASURED IN PCT HARVESTED" -> "Corn, Grain"
    return short_desc.split(" - ")[0].title()


def _get(s, key, **params):
    params = {"key": key, "format": "JSON", "source_desc": "SURVEY",
              "sector_desc": "CROPS", "agg_level_desc": "NATIONAL", **params}
    r = s.get(API, params=params, timeout=90)
    if r.status_code == 400 and "exceeds limit" in r.text.lower():
        raise RuntimeError("Quick Stats row limit exceeded – narrow the query")
    r.raise_for_status()
    return r.json().get("data", [])


def _val(v):
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None   # "(D)", "(NA)" etc.


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _nearest(series: dict[date, float], target: date, tol_days=4, fill=False):
    """Return (value, method) for the week of `target`.

    method is "observed" when a report falls within tol_days,
    "interpolated" when a reporting gap is filled linearly (for example the
    October-November 2025 shutdown), "carried" when the season has finished
    and the last report is reused, "assumed" when the season has not started
    and the historical filler is 0, or None when no value is returned.
    """
    best = None
    for d, v in series.items():
        if abs((d - target).days) <= tol_days and (best is None or abs((d - target).days) < abs((best[0] - target).days)):
            best = (d, v)
    if best or not fill:
        return (best[1], "observed") if best else (None, None)
    before = [d for d in series if target - timedelta(days=70) <= d < target]
    after = [d for d in series if target < d <= target + timedelta(days=70)]
    if before and after:          # gap in reporting (e.g. Oct-Nov 2025 shutdown): interpolate
        b, a = max(before), min(after)
        w = (target - b).days / (a - b).days
        return series[b] + w * (series[a] - series[b]), "interpolated"
    if fill == "interp":
        return None, None
    if before:                    # season finished, reporting stopped -> carry last value
        return series[max(before)], "carried"
    if after:                     # season not started yet that year
        return 0.0, "assumed"
    return None, None


def _quality_label(method: str | None) -> str | None:
    if method == "interpolated":
        return "interpolated"
    if method in ("carried", "assumed"):
        return "estimated"
    return None


def _window(series: dict[date, float], latest: date, fill):
    """Previous week, last year, and 5-year average for the week of `latest`.

    When the published average uses an interpolated or estimated year, the
    average of the observed years alone is returned as well. That observed
    average is None when fewer than three observed years remain.
    """
    prev, _prev_method = _nearest(series, latest - timedelta(days=7), 1)
    last_year, last_method = _nearest(series, latest - timedelta(days=364), fill=fill)
    parts = []
    for k in range(1, 6):
        value, method = _nearest(series, latest - timedelta(days=364 * k), fill=fill)
        if value is not None:
            parts.append((value, method))
    avg5 = sum(v for v, _method in parts) / len(parts) if len(parts) >= 3 else None
    quality = {}
    observed_n = None
    avg5_observed = None
    label = _quality_label(last_method)
    if label:
        quality["last_year"] = label
    if avg5 is not None and any(method != "observed" for _value, method in parts):
        quality["avg5"] = "interpolated" if any(method == "interpolated" for _value, method in parts) else "estimated"
        observed = [v for v, method in parts if method == "observed"]
        observed_n = len(observed)
        avg5_observed = sum(observed) / len(observed) if observed_n >= 3 else None
    return prev, last_year, avg5, quality, avg5_observed, observed_n


def parse(rows: list[dict], today: date | None = None) -> tuple[str, list[dict]]:
    """rows: raw Quick Stats records for PROGRESS and CONDITION (5+ years).
    Returns (report_date, normalized rows). 5-yr average and last year are
    computed from history by matching week-ending dates (±4 days), which is
    how USDA's tables line up week-to-week."""
    prog = defaultdict(dict)   # (crop, stage) -> {week_ending: value}
    cond = defaultdict(lambda: defaultdict(dict))  # crop -> week -> {bucket: value}
    for r in rows:
        if not r.get("week_ending"):
            continue
        cat = r.get("statisticcat_desc")
        v = _val(r.get("Value"))
        if v is None:
            continue
        we = _d(r["week_ending"])
        crop = crop_label(r["short_desc"])
        unit = r.get("unit_desc", "")
        if cat == "PROGRESS" and unit.startswith("PCT "):
            stage = unit[4:]
            prog[(crop, STAGE_MAP.get(stage, stage.lower()))][we] = v
        elif cat == "CONDITION" and unit in CONDITION_UNITS:
            cond[crop][we][CONDITION_UNITS[unit]] = v

    all_weeks = [w for s in prog.values() for w in s] + [w for c in cond.values() for w in c]
    if not all_weeks:
        return None, []
    latest = max(all_weeks)
    out = []

    for (crop, stage), series in sorted(prog.items()):
        if latest not in series:
            continue  # not active this week
        cur = series[latest]
        prev, ly, avg5, quality, avg5_obs, observed_n = _window(series, latest, fill=True)
        out.append(rec(crop, stage, cur, prev_week=prev, last_year=ly, avg5=avg5,
                       region="United States", quality=quality or None,
                       avg5_observed=avg5_obs, avg5_observed_n=observed_n))

    def ge(d):
        return (d.get("gd") or 0) + (d.get("ex") or 0) if d else None

    for crop, weeks in sorted(cond.items()):
        if latest not in weeks:
            continue
        cur = weeks[latest]
        series_ge = {w: ge(d) for w, d in weeks.items()}
        prev, ly, avg5, quality, avg5_obs, observed_n = _window(series_ge, latest, fill="interp")
        out.append(rec(crop, "condition_ge", ge(cur), prev_week=prev, last_year=ly, avg5=avg5,
                       region="United States", dist=cur, quality=quality or None,
                       avg5_observed=avg5_obs, avg5_observed_n=observed_n))
    return latest.isoformat(), out


_MONTHS = {n: i for i, n in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
_PROGRESS = {
    "Corn Harvested": ("Corn", "harvested"),
    "Soybeans Harvested": ("Soybeans", "harvested"),
    "Cotton Harvested": ("Cotton", "harvested"),
    "Cotton Bolls Opening": ("Cotton", "bolls opening"),
    "Peanuts Harvested": ("Peanuts", "harvested"),
    "Sunflowers Harvested": ("Sunflower", "harvested"),
    "Winter Wheat Planted": ("Wheat, Winter", "planted"),
    "Winter Wheat Emerged": ("Wheat, Winter", "emerged"),
    "Sorghum Harvested": ("Sorghum", "harvested"),
}


def _pct(tok: str):
    tok = tok.strip()
    if tok in {"(NA)", "NA", "-", ""}:
        return None
    return float(tok.replace(",", ""))


def _parse_published(text: str) -> dict:
    """National rows from the printed Crop Progress report.

    The 5-year average is the number in the report. It is not recomputed.
    A cell printed (NA) stays missing.
    """
    released = re.search(r"Released (\w+ \d{1,2}, \d{4})", text)
    week = re.search(
        r"(\w+ \d{1,2}),\s*:\s*\w+ \d{1,2},\s*:\s*(\w+ \d{1,2}),\s*:.*?(\d{4})\s*:\s*\d{4}\s*:\s*(\d{4})",
        text, re.S)
    if not week:
        raise ValueError("crop progress week-ending dates were not read")
    month_name, day = week.group(2).split()
    report_date = date(int(week.group(4)), _MONTHS[month_name], int(day)).isoformat()
    rows = []
    sections = re.split(r"\n(?=[A-Z][A-Za-z0-9, ]+ - )", text)
    for section in sections:
        title = section.split("\n", 1)[0].strip()
        spec = next((v for k, v in _PROGRESS.items() if title.startswith(k)), None)
        if spec:
            total = re.search(r"^\s*\d+ States \.*:\s*(.+)$", section, re.M)
            if not total:
                continue
            nums = re.findall(r"\([A-Z]+\)|-|\d+", total.group(1))
            if len(nums) < 4:
                continue
            last_year, prev, current, avg5 = (_pct(n) for n in nums[:4])
            if current is None:
                continue
            rows.append(rec(spec[0], spec[1], current, prev_week=prev, last_year=last_year, avg5=avg5,
                            region="United States"))
        elif title.startswith("Winter Wheat Condition"):
            total = re.search(r"^\s*18 States \.*:\s*(.+)$", section, re.M)
            prev = re.search(r"^\s*Previous week \.*:\s*(.+)$", section, re.M)
            last = re.search(r"^\s*Previous year \.*:\s*(.+)$", section, re.M)
            if not total:
                continue
            def five(line):
                vals = [_pct(n) for n in re.findall(r"\([A-Z]+\)|-|\d+", line)]
                return vals[:5]
            cur = five(total.group(1))
            if len(cur) < 5 or cur[3] is None or cur[4] is None:
                continue
            prv = five(prev.group(1)) if prev else [None] * 5
            lyr = five(last.group(1)) if last else [None] * 5
            ge = cur[3] + cur[4]
            ge_prev = (prv[3] + prv[4]) if prv[3] is not None and prv[4] is not None else None
            ge_ly = (lyr[3] + lyr[4]) if lyr[3] is not None and lyr[4] is not None else None
            rows.append(rec(
                "Wheat, Winter", "condition_ge", ge, prev_week=ge_prev, last_year=ge_ly, avg5=None,
                region="United States",
                dist={"vp": cur[0], "pr": cur[1], "fr": cur[2], "gd": cur[3], "ex": cur[4]},
            ))
    if len(rows) < 2:
        raise ValueError(f"published crop progress parsed {len(rows)} national rows")
    validate(rows, min_rows=2)
    return payload(
        "us", "United States", "USDA NASS Crop Progress", SOURCE_URL, report_date, rows,
        notes=[
            "National row of the printed Crop Progress report. The 5-year average is the figure NASS prints.",
            "A cell printed (NA) is not available. It is not filled in.",
            "Condition is good plus excellent from the printed shares." + (
                f" Released {released.group(1)}." if released else ""
            ),
        ],
    )


def fetch() -> dict:
    # The printed report carries this week, the prior week, last year and the
    # 5-year average. Prefer it so a missing Quick Stats key cannot blank the page.
    try:
        return _parse_published(_published_text())
    except Exception as published_error:
        key = env("NASS_API_KEY")
        if not key:
            raise RuntimeError(
                f"published Crop Progress report was not read ({published_error}), and NASS_API_KEY is not set"
            ) from published_error
    s = session()
    y0 = date.today().year - 6
    raw = []
    for cat in ("PROGRESS", "CONDITION"):
        raw += _get(s, key, statisticcat_desc=cat, year__GE=str(y0))
    report_date, rows = parse(raw)
    validate(rows, min_rows=2)
    return payload("us", "United States", "USDA NASS Crop Progress", SOURCE_URL, report_date, rows,
                   notes=["Week-ending date shown. Last year and the 5-year average are matched to the same calendar week.",
                          "Weeks with no published report (for example the October-November 2025 shutdown) are linearly interpolated and marked on each figure.",
                          "A finished season reuses the last published figure, and a season that has not started is entered as 0. Both are marked as estimated.",
                          "Condition is the share rated good or excellent."])

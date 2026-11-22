#!/usr/bin/env python3
"""Weather for the glance table.

Daily series are UTC. Normals are the 10-year ERA5 mean of the same calendar
window, cached so later runs do not repeat the archive calls. The forecast is
read at most once per UTC day. SEAS5, the CPC ENSO line, and USDM drought are
non-fatal: a failure leaves a dash and still publishes the station table.

Open-Meteo calls, when a refresh is actually due:
  1 forecast request for every station, 10 archive requests only when the
  cached normals do not cover today's windows, and up to 3 seasonal requests.
"""
import csv
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "weather_data.json")
NORMALS = os.path.join(ROOT, "data", "weather_normals.json")
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
SEASONAL_URL = "https://seasonal-api.open-meteo.com/v1/seasonal"
WKST_URL = "https://www.cpc.ncep.noaa.gov/data/indices/wksst9120.for"
ENSO_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml"
USDM_URL = (
    "https://usdmdataservices.unl.edu/api/StateStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
)

# division, station label, region, lat, lon, USDM state FIPS or None.
# The 30 Research stations, in the order MJ asked for. Coffee, sugar and cocoa
# origins are not on this page.
REGIONS = [
    ("Canada", "Saskatoon, SK", "Central SK", 52.1, -106.7, None),
    ("Canada", "Regina, SK", "Southern SK", 50.5, -104.6, None),
    ("Canada", "Brandon, MB", "SW Manitoba", 49.8, -99.9, None),
    ("Canada", "Red Deer, AB", "Central Alberta", 52.3, -113.8, None),
    ("Canada", "Grande Prairie, AB", "Peace River", 55.2, -118.8, None),
    ("United States", "Fargo, ND", "Red River Valley", 46.9, -96.8, "38"),
    ("United States", "Redwood Falls, MN", "Northern Corn Belt", 44.5, -95.1, "27"),
    ("United States", "Ames, IA", "Western Corn Belt", 42.0, -93.5, "19"),
    ("United States", "York, NE", "Western Corn Belt", 40.9, -97.6, "31"),
    ("United States", "Decatur, IL", "Eastern Corn Belt", 39.8, -89.0, "17"),
    ("United States", "Lyons, KS", "HRW Belt", 38.5, -98.0, "20"),
    ("United States", "Lubbock, TX", "Southern Plains", 33.5, -101.5, "48"),
    ("Brazil", "Lucas do Rio Verde, MT", "Mato Grosso", -13.0, -56.0, None),
    ("Brazil", "Rio Verde, GO", "Center-West", -17.8, -50.9, None),
    ("Brazil", "Cascavel, PR", "Southern Brazil", -24.9, -53.5, None),
    ("Brazil", "Passo Fundo, RS", "Far South Brazil", -28.3, -52.4, None),
    ("Argentina", "Rosario, Santa Fe", "Core Pampas", -33.0, -61.0, None),
    ("Argentina", "Tres Arroyos, Buenos Aires", "Southern Pampas", -38.0, -60.3, None),
    ("Europe / Black Sea", "Melun, France", "Paris Basin", 48.5, 2.5, None),
    ("Europe / Black Sea", "Magdeburg, Saxony-Anhalt DE", "Eastern Germany", 52.1, 11.6, None),
    ("Europe / Black Sea", "Călărași, RO", "Danube Plain", 44.2, 27.3, None),
    ("Europe / Black Sea", "Cherkasy, UA", "Central Ukraine", 49.0, 32.0, None),
    ("Europe / Black Sea", "Belorechensk, Krasnodar RU", "Southern Russia", 45.0, 40.0, None),
    ("China", "Zhengzhou, Henan", "North China Plain", 34.5, 114.0, None),
    ("China", "Harbin, Heilongjiang", "Northeast China", 46.0, 126.5, None),
    ("SE Asia (palm)", "Kluang, Johor MY", "Peninsular Malaysia", 2.0, 103.3, None),
    ("SE Asia (palm)", "Pekanbaru, Riau ID", "Sumatra", 0.5, 101.4, None),
    ("Australia", "Cunderdin, WA", "WA Wheatbelt", -31.5, 117.0, None),
    ("Australia", "Horsham, VIC", "Wimmera", -36.7, 142.2, None),
    ("Australia", "Dubbo, NSW", "Central West NSW", -32.5, 148.5, None),
]

OUTLOOK_VARS = {
    "temp_anom": ["temperature_2m_anomaly"],
    "precip_anom": ["precipitation_anomaly"],
    "precip_mean": ["precipitation_mean", "precipitation_sum"],
}
OUTLOOK_MONTHS = 3
HISTORY_YEARS = 10
PAST_DAYS = 92
FORECAST_DAYS = 16
# Extra days on each side of the windows so the cache stays valid as the
# calendar advances, without another archive fetch.
NORMAL_PAD = 21
MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def http_get_json(url, params, max_attempts=4):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{qs}", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    })
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < max_attempts:
                wait = 15 * attempt
                print(f"\n    HTTP {e.code} — retrying in {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise
        except OSError as e:
            if attempt < max_attempts:
                wait = 10 * attempt
                print(f"\n    network error ({e}) — retrying in {wait}s", flush=True)
                time.sleep(wait)
                continue
            raise


def http_get_text(url, max_attempts=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read()
            return raw.decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            if attempt < max_attempts:
                time.sleep(5 * attempt)
                continue
            raise last


def as_location_list(data, expected, label):
    if isinstance(data, dict):
        data = [data]
    if len(data) != expected:
        raise RuntimeError(f"{label} returned {len(data)} locations, expected {expected}")
    return data


def anchor_for_year(today, year):
    try:
        return today.replace(year=year)
    except ValueError:
        return today.replace(year=year, day=28)


def series_to_dict(block):
    daily = block.get("daily") or {}
    times = daily.get("time") or []
    out = {}
    n = len(times)
    for i, d in enumerate(times):
        out[d] = {
            "precip": (daily.get("precipitation_sum") or [None] * n)[i],
            "tmax": (daily.get("temperature_2m_max") or [None] * n)[i],
            "tmin": (daily.get("temperature_2m_min") or [None] * n)[i],
        }
    return out


def window_sum(series, start, end, key):
    vals = []
    d = start
    while d <= end:
        rec = series.get(d.isoformat())
        if rec and rec.get(key) is not None:
            vals.append(rec[key])
        d += timedelta(days=1)
    return sum(vals) if vals else None


def window_avg_temp(series, start, end):
    vals = []
    d = start
    while d <= end:
        rec = series.get(d.isoformat())
        if rec and rec.get("tmax") is not None and rec.get("tmin") is not None:
            vals.append((rec["tmax"] + rec["tmin"]) / 2.0)
        d += timedelta(days=1)
    return (sum(vals) / len(vals)) if vals else None


def window_extreme_temps(series, start, end):
    tmaxes, tmins = [], []
    d = start
    while d <= end:
        rec = series.get(d.isoformat())
        if rec:
            if rec.get("tmax") is not None:
                tmaxes.append(rec["tmax"])
            if rec.get("tmin") is not None:
                tmins.append(rec["tmin"])
        d += timedelta(days=1)
    return (max(tmaxes) if tmaxes else None, min(tmins) if tmins else None)


def pct_of_normal(actual, normal):
    if actual is None or normal is None or normal == 0:
        return None
    return (actual / normal) * 100.0


def avg(lst):
    return (sum(lst) / len(lst)) if lst else None


def round_or_none(value, places):
    if value is None:
        return None
    return round(float(value), places)


def next_months(today, k):
    y, m = today.year, today.month
    out = []
    for _ in range(k):
        m += 1
        if m == 13:
            y, m = y + 1, 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def month_label(months):
    first, last = months[0], months[-1]
    return f"{MONTH_ABBR[int(first[5:7]) - 1]}–{MONTH_ABBR[int(last[5:7]) - 1]}"


def station_key():
    return [r[1] for r in REGIONS]


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def forecast_already_today(doc):
    """True when today's file already has this station list. WEATHER_FORCE refreshes it."""
    if os.environ.get("WEATHER_FORCE"):
        return False
    if not doc or doc.get("_meta", {}).get("fetched_at", "")[:10] != date.today().isoformat():
        return False
    regions = doc.get("regions") or {}
    if list(regions) != station_key():
        return False
    sample = next(iter(regions.values()), {})
    return "precip_fc_1_7_mm" in sample and "region" in sample


def normals_cover(cache, today):
    if not cache or cache.get("stations") != station_key():
        return False
    built = cache.get("built_for")
    try:
        built_day = datetime.strptime(built, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return False
    if abs((today - built_day).days) > NORMAL_PAD:
        return False
    series = cache.get("series") or {}
    return all(name in series and series[name] for name in station_key())


def unpack_series(packed):
    out = {}
    for day, triple in (packed or {}).items():
        if not isinstance(triple, list) or len(triple) != 3:
            continue
        out[day] = {"precip": triple[0], "tmax": triple[1], "tmin": triple[2]}
    return out


def pack_series(series):
    return {
        day: [rec.get("precip"), rec.get("tmax"), rec.get("tmin")]
        for day, rec in series.items()
    }


def fetch_forecast_block(n, lats, lons):
    params = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "past_days": PAST_DAYS,
        "forecast_days": FORECAST_DAYS,
        "timezone": "UTC",
    }
    return as_location_list(http_get_json(FORECAST_URL, params), n, "Forecast API")


def fetch_archive_block(n, lats, lons, start_date, end_date):
    params = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
        "timezone": "UTC",
    }
    return as_location_list(http_get_json(ARCHIVE_URL, params), n, "Archive API")


def fetch_history(n, lats, lons, today):
    merged = [dict() for _ in range(n)]
    for yr_offset in range(1, HISTORY_YEARS + 1):
        anchor = anchor_for_year(today, today.year - yr_offset)
        start = anchor - timedelta(days=89 + NORMAL_PAD)
        end = anchor + timedelta(days=14 + NORMAL_PAD)
        print(f"    archive {anchor.year}: {start} to {end}", flush=True)
        blocks = fetch_archive_block(n, lats, lons, start, end)
        for i, block in enumerate(blocks):
            merged[i].update(series_to_dict(block))
        if yr_offset < HISTORY_YEARS:
            time.sleep(2)
    return merged


def save_normals(today, histories):
    series = {}
    for ( _div, name, _region, _lat, _lon, _fips), hist in zip(REGIONS, histories):
        series[name] = pack_series(hist)
    doc = {
        "built_for": today.isoformat(),
        "source": "Open-Meteo archive, ERA5, UTC daily",
        "history_years": HISTORY_YEARS,
        "pad_days": NORMAL_PAD,
        "stations": station_key(),
        "series": series,
    }
    os.makedirs(os.path.dirname(NORMALS), exist_ok=True)
    with open(NORMALS, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
        f.write("\n")
    print(f"  cached normals {os.path.getsize(NORMALS):,} bytes")
    return doc


def load_histories(today, lats, lons):
    cache = load_json(NORMALS)
    if normals_cover(cache, today):
        print("  ERA5 normals cache covers this window — not calling the archive")
        return [unpack_series(cache["series"][name]) for name in station_key()]
    print(f"  Archive API ({HISTORY_YEARS} years, {len(REGIONS)} stations, cached for {NORMAL_PAD} days)...")
    histories = fetch_history(len(REGIONS), lats, lons, today)
    save_normals(today, histories)
    return histories


def fetch_seasonal_var(n, lats, lons, token):
    params = {
        "latitude": ",".join(str(x) for x in lats),
        "longitude": ",".join(str(x) for x in lons),
        "monthly": token,
    }
    blocks = as_location_list(http_get_json(SEASONAL_URL, params), n, f"Seasonal API ({token})")
    out = []
    for block in blocks:
        monthly = block.get("monthly") or {}
        times = monthly.get("time")
        key = next((k for k in monthly if k == token or k.startswith(token + "_")), None)
        if not times or key is None:
            raise ValueError(f"no monthly '{token}'")
        out.append({t[:7]: v for t, v in zip(times, monthly[key])})
    return out


def fetch_outlook(n, lats, lons, today):
    months = next_months(today, OUTLOOK_MONTHS)
    label = month_label(months)
    empty = [{"outlook_temp_dep_c": None, "outlook_precip_pct_normal": None} for _ in range(n)]
    try:
        series, problems = {}, []
        for var, candidates in OUTLOOK_VARS.items():
            got = None
            for token in candidates:
                try:
                    got = fetch_seasonal_var(n, lats, lons, token)
                    print(f"    outlook {var}: {token}")
                    break
                except Exception as e:
                    print(f"    outlook {var}: '{token}' failed: {e}")
            series[var] = got
            if got is None:
                problems.append(var)
        results = []
        for i in range(n):
            temp_dep = precip_pct = None
            t = series.get("temp_anom")
            if t:
                vals = [t[i].get(m) for m in months]
                if all(v is not None for v in vals):
                    temp_dep = sum(vals) / len(vals)
            pa, pm = series.get("precip_anom"), series.get("precip_mean")
            if pa and pm:
                anoms = [pa[i].get(m) for m in months]
                means = [pm[i].get(m) for m in months]
                if all(v is not None for v in anoms + means):
                    normal = sum(means) - sum(anoms)
                    if normal > 0:
                        precip_pct = sum(means) / normal * 100.0
            results.append({"outlook_temp_dep_c": temp_dep, "outlook_precip_pct_normal": precip_pct})
        error = None
        if problems:
            error = "could not get: " + ", ".join(problems)
        elif all(r["outlook_temp_dep_c"] is None and r["outlook_precip_pct_normal"] is None for r in results):
            error = f"no data for {months[0]}..{months[-1]}"
        return results, label, error
    except Exception as e:
        return empty, label, f"{type(e).__name__}: {e}"


def mean_normal(hist, today, start_offset, end_offset, kind):
    """Mean of one window across the 10 prior years. Offsets are days from the anchor."""
    vals = []
    for yr_offset in range(1, HISTORY_YEARS + 1):
        anchor = anchor_for_year(today, today.year - yr_offset)
        start = anchor + timedelta(days=start_offset)
        end = anchor + timedelta(days=end_offset)
        if kind == "precip":
            v = window_sum(hist, start, end, "precip")
        else:
            v = window_avg_temp(hist, start, end)
        if v is not None:
            vals.append(v)
    return avg(vals)


def departure(actual, normal):
    if actual is None or normal is None:
        return None
    return actual - normal


def parse_nino_week(text):
    """Latest weekly Niño-3.4 anomaly from CPC wksst9120.for. Returns (iso date, anomaly) or None."""
    last = None
    for line in text.splitlines():
        m = re.match(r"\s*(\d{2})([A-Z]{3})(\d{4})\s+(.*)$", line)
        if not m or m.group(2) not in MONTHS:
            continue
        nums = re.findall(r"[+-]?\d+\.\d+", m.group(4))
        if len(nums) < 6:
            continue
        # Four regions, SST then anomaly. Niño-3.4 is the third pair.
        anomaly = float(nums[5])
        day = date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)))
        last = (day.isoformat(), anomaly)
    return last


def parse_enso_status(page):
    text = html.unescape(page)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    m = re.search(r"ENSO Alert System Status:\s*(.+?)\s+Synopsis:", text)
    if not m:
        return None
    status = m.group(1).strip(" :\u00a0")
    return status or None


def fetch_enso():
    try:
        page = http_get_text(ENSO_URL)
        table = http_get_text(WKST_URL)
        status = parse_enso_status(page)
        week = parse_nino_week(table)
        if not status and not week:
            return {"status": None, "nino34": None, "week": None, "error": "CPC pages had no status or Niño-3.4 row"}
        return {
            "status": status,
            "nino34": None if not week else week[1],
            "week": None if not week else week[0],
            "error": None,
            "source": "CPC ENSO diagnostic discussion and wksst9120.for",
        }
    except Exception as e:
        return {"status": None, "nino34": None, "week": None, "error": f"{type(e).__name__}: {e}"}


def parse_usdm_csv(text):
    """D1 in this feed is the cumulative percent in D1 or worse. Returns the last two weeks."""
    rows = list(csv.DictReader(io.StringIO(text)))
    if len(rows) < 1 or "D1" not in rows[0]:
        return None
    latest = rows[0]
    prior = rows[1] if len(rows) > 1 else None
    d1 = float(latest["D1"])
    change = None if prior is None else d1 - float(prior["D1"])
    week = latest.get("ValidStart") or latest.get("MapDate")
    return {
        "code": latest.get("StateAbbreviation"),
        "d1_pct": round(d1, 1),
        "change": None if change is None else round(change, 1),
        "week": week,
    }


def fetch_drought():
    seen = []
    states = []
    error = None
    for _div, _name, _region, _lat, _lon, fips in REGIONS:
        if not fips or fips in seen:
            continue
        seen.append(fips)
        start = (date.today() - timedelta(days=40)).isoformat()
        end = date.today().isoformat()
        url = f"{USDM_URL}?aoi={fips}&startdate={start}&enddate={end}&statisticsType=1"
        try:
            parsed = parse_usdm_csv(http_get_text(url, max_attempts=2))
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            parsed = None
        if parsed:
            states.append(parsed)
        else:
            error = error or f"no D1 row for FIPS {fips}"
    if not states:
        return {"states": [], "week": None, "error": error or "USDM returned nothing"}
    return {
        "states": states,
        "week": states[0].get("week"),
        "error": error,
        "source": "USDM StateStatistics percent of area, statisticsType=1. D1 is D1 or worse.",
    }


def build_station(row, fc_series, hist, outlook):
    _div, name, region, lat, lon, _fips = row
    today = date.today()
    windows = {
        "precip_90d": (-89, 0, "precip"),
        "precip_30d": (-29, 0, "precip"),
        "temp_7d": (-6, 0, "temp"),
        "temp_1_7": (1, 7, "temp"),
        "precip_1_7": (1, 7, "precip"),
        "temp_8_14": (8, 14, "temp"),
        "precip_8_14": (8, 14, "precip"),
    }
    actual = {}
    for key, (a, b, kind) in windows.items():
        start, end = today + timedelta(days=a), today + timedelta(days=b)
        if kind == "precip":
            actual[key] = window_sum(fc_series, start, end, "precip")
        else:
            actual[key] = window_avg_temp(fc_series, start, end)
    hi, lo = window_extreme_temps(fc_series, today + timedelta(days=1), today + timedelta(days=14))
    normal = {key: mean_normal(hist, today, a, b, kind) for key, (a, b, kind) in windows.items()}
    return {
        "division": row[0],
        "region": region,
        "latitude": lat,
        "longitude": lon,
        "reading": "point",
        "precip_90d_pct_normal": round_or_none(pct_of_normal(actual["precip_90d"], normal["precip_90d"]), 1),
        "precip_90d_mm": round_or_none(actual["precip_90d"], 1),
        "precip_30d_pct_normal": round_or_none(pct_of_normal(actual["precip_30d"], normal["precip_30d"]), 1),
        "precip_30d_mm": round_or_none(actual["precip_30d"], 1),
        "temp_dep_7d_c": round_or_none(departure(actual["temp_7d"], normal["temp_7d"]), 2),
        "temp_dep_fc_1_7_c": round_or_none(departure(actual["temp_1_7"], normal["temp_1_7"]), 2),
        "precip_fc_1_7_pct_normal": round_or_none(pct_of_normal(actual["precip_1_7"], normal["precip_1_7"]), 1),
        "precip_fc_1_7_mm": round_or_none(actual["precip_1_7"], 1),
        "temp_dep_fc_8_14_c": round_or_none(departure(actual["temp_8_14"], normal["temp_8_14"]), 2),
        "precip_fc_8_14_pct_normal": round_or_none(pct_of_normal(actual["precip_8_14"], normal["precip_8_14"]), 1),
        "precip_fc_8_14_mm": round_or_none(actual["precip_8_14"], 1),
        "temp_14d_forecast_hi_c": round_or_none(hi, 1),
        "temp_14d_forecast_lo_c": round_or_none(lo, 1),
        "outlook_temp_dep_c": round_or_none(outlook["outlook_temp_dep_c"], 2),
        "outlook_precip_pct_normal": round_or_none(outlook["outlook_precip_pct_normal"], 1),
    }


def write_weather(doc):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(doc, f, separators=(",", ":"))
        f.write("\n")


def main():
    today = date.today()
    existing = load_json(OUT)
    if forecast_already_today(existing):
        print(f"Weather forecast already fetched today ({existing['_meta']['fetched_at']}). Skipping Open-Meteo.")
        return
    n = len(REGIONS)
    lats = [r[3] for r in REGIONS]
    lons = [r[4] for r in REGIONS]
    print(f"Weather glance: {n} stations")
    try:
        histories = load_histories(today, lats, lons)
        print(f"  Forecast API (past {PAST_DAYS}d + next {FORECAST_DAYS}d)...", flush=True)
        fc_blocks = fetch_forecast_block(n, lats, lons)
    except Exception as e:
        print(f"ERROR: Open-Meteo forecast or archive failed: {e}", file=sys.stderr)
        print("Last good weather file was kept.", file=sys.stderr)
        sys.exit(1)

    print("  SEAS5 outlook (non-fatal):")
    outlook, outlook_label, outlook_error = fetch_outlook(n, lats, lons, today)
    if outlook_error:
        print(f"WARNING: seasonal outlook unavailable — {outlook_error}", file=sys.stderr)
        print(f"::warning title=Weather outlook unavailable::{outlook_error}")

    print("  ENSO and US drought (non-fatal)")
    enso = fetch_enso()
    drought = fetch_drought()
    if enso.get("error"):
        print(f"WARNING: ENSO unavailable — {enso['error']}", file=sys.stderr)
    if drought.get("error"):
        print(f"WARNING: USDM incomplete — {drought['error']}", file=sys.stderr)

    regions = {}
    missing = []
    for i, row in enumerate(REGIONS):
        fc_series = series_to_dict(fc_blocks[i])
        if not fc_series or not histories[i]:
            missing.append(row[1])
            continue
        regions[row[1]] = build_station(row, fc_series, histories[i], outlook[i])
    if missing:
        print(f"ERROR: no series for {missing}. Last good file kept.", file=sys.stderr)
        sys.exit(1)
    broken = [name for name, d in regions.items() if d["precip_30d_mm"] is None and d["precip_90d_mm"] is None]
    if broken:
        print(f"ERROR: precip empty for {broken}. Last good file kept.", file=sys.stderr)
        sys.exit(1)

    doc = {
        "_meta": {
            "fetched_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "Open-Meteo forecast (UTC daily). Normals: 10-year ERA5 mean of the same calendar window.",
            "history_years": HISTORY_YEARS,
            "order": station_key(),
            "outlook_label": outlook_label,
            "outlook_source": "ECMWF SEAS5 ensemble mean versus the model's own climate, next 3 months",
            "outlook_error": outlook_error,
            "enso": enso,
            "drought": drought,
        },
        "regions": regions,
    }
    write_weather(doc)
    print(f"Saved {OUT} ({os.path.getsize(OUT):,} bytes), {len(regions)} stations")


if __name__ == "__main__":
    main()

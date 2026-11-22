#!/usr/bin/env python3
"""Mechanical signals for the summary page. Every cell is a rule over files already in data/.

A missing input, a short history, or a date older than its cadence is a dash.
Nothing here is filled in by judgment.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CONFIG_PATH = os.path.join(ROOT, "config", "signals.json")
OUT = os.path.join(DATA, "signals.json")

TODAY = date.today()


def load_json(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def percentile_at_or_below(value, sample):
    """Share of sample values at or below `value`, in percent."""
    if value is None or not sample:
        return None
    return 100.0 * sum(1 for x in sample if x <= value) / len(sample)


def page_stu_percentile(values):
    """Stocks/use rank used by the Fundamentals page (index.html stuPctile).

    `values` is every year on that balance sheet, current year included.
    The rank is count(x <= current) / number of years * 100.
    """
    if not values:
        return None
    return percentile_at_or_below(values[-1], values)


def band(value, low_is, high_is, low, high):
    """low_is is the state when value <= low. high_is when value >= high."""
    if value is None:
        return None
    if value <= low:
        return low_is
    if value >= high:
        return high_is
    return "neutral"


def stu_state(percentile, revision, cfg):
    if percentile is None:
        return None
    state = band(percentile, "bullish", "bearish", cfg["stu_bull_pct"], cfg["stu_bear_pct"])
    if revision is None or state == "neutral":
        return state
    # A positive stocks revision is looser. It disagrees with a tight (bullish) reading.
    if state == "bullish" and revision > 0:
        return "neutral"
    if state == "bearish" and revision < 0:
        return "neutral"
    return state


def extension_state(percentile, cfg):
    if percentile is None:
        return None
    if percentile >= cfg["mm_ext_long_pct"]:
        return "bearish"
    if percentile <= cfg["mm_ext_short_pct"]:
        return "bullish"
    return "neutral"


def flow_state(chg1, chg4):
    if chg1 is None or chg4 is None:
        return None
    if chg1 > 0 and chg4 > 0:
        return "bullish"
    if chg1 < 0 and chg4 < 0:
        return "bearish"
    return "neutral"


def level_vs_avg_state(pct, cfg):
    return band(pct, "bullish", "bearish", -cfg["energy_vs_avg_pct"], cfg["energy_vs_avg_pct"])


def change_vs_norm_state(delta_pp, cfg):
    # A build larger than the same week of the prior five years is bearish.
    return band(delta_pp, "bullish", "bearish", -cfg["energy_change_vs_norm_pp"], cfg["energy_change_vs_norm_pp"])


def yoy_pct_state(pct, low, high):
    return band(pct, "bullish", "bearish", low, high)


def condition_state(delta_pp, cfg):
    # A crop worse than the comparison is bullish.
    return band(delta_pp, "bullish", "bearish", -cfg["condition_pp"], cfg["condition_pp"])


def demand_pace_state(delta_pp, cfg):
    return band(delta_pp, "bearish", "bullish", -cfg["demand_pp"], cfg["demand_pp"])


def canola_export_state(yoy_pct, cfg):
    return band(yoy_pct, "bearish", "bullish", -cfg["demand_pp"], cfg["demand_pp"])


def rescore(rule_id, inputs, cfg):
    """Replay a stored cell from its inputs. Used by the trust test."""
    if not inputs:
        return None
    if rule_id == "stu":
        return stu_state(inputs.get("percentile"), inputs.get("revision"), cfg)
    if rule_id == "mm_extension":
        return extension_state(inputs.get("percentile"), cfg)
    if rule_id == "mm_flow":
        return flow_state(inputs.get("change_1w"), inputs.get("change_4w"))
    if rule_id == "energy_level":
        return level_vs_avg_state(inputs.get("vs_avg_pct"), cfg)
    if rule_id == "energy_change":
        return change_vs_norm_state(inputs.get("delta_pp"), cfg)
    if rule_id == "cattle_yoy":
        return yoy_pct_state(inputs.get("pct"), cfg["cattle_yoy_low"], cfg["cattle_yoy_high"])
    if rule_id == "cattle_demand":
        return band(inputs.get("pct"), "bearish", "bullish", cfg["cattle_yoy_low"], cfg["cattle_yoy_high"])
    if rule_id == "condition":
        return condition_state(inputs.get("delta_pp"), cfg)
    if rule_id == "demand_pace":
        return demand_pace_state(inputs.get("delta_pp"), cfg)
    if rule_id in ("canola_exports", "demand_yoy"):
        limit = cfg["demand_pp"]
        return band(inputs.get("yoy_pct"), "bearish", "bullish", -limit, limit)
    if rule_id == "seasonal":
        return seasonal_state(inputs.get("average"), cfg)
    return None


def parse_day(value):
    if not value:
        return None
    text = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.strptime(str(value), "%B %d, %Y").date()
    except ValueError:
        return None


def age_days(day):
    parsed = day if isinstance(day, date) else parse_day(day)
    if parsed is None:
        return None
    return (TODAY - parsed).days


def cell(state, rule_id, as_of, inputs, detail, cadence_key, cfg, reason=None):
    day = parse_day(as_of) if not isinstance(as_of, date) else as_of
    as_text = day.isoformat() if isinstance(day, date) else None
    rec = {
        "state": state,
        "rule_id": rule_id,
        "as_of": as_text,
        "inputs": inputs or {},
        "detail": detail,
        "reason": reason,
    }
    if state is None:
        rec["text"] = None
        return rec
    if cadence_key is None:
        rec["text"] = figure_text(rule_id, state, inputs)
        return rec
    limit = cfg["cadence_days"][cadence_key]
    old = age_days(day)
    if old is None or old > limit:
        rec["state"] = None
        rec["text"] = None
        rec["reason"] = f"stale: {as_text or 'undated'} is older than {limit} days"
        return rec
    rec["text"] = figure_text(rule_id, state, inputs)
    return rec


GLYPH = {"bullish": "▲", "bearish": "▼", "neutral": ""}


def k_contracts(n):
    value = abs(n) / 1000.0
    body = f"{value:.0f}k" if value >= 100 else f"{value:.1f}k"
    sign = "-" if n < 0 else "+" if n > 0 else ""
    return sign + body


def figure_text(rule_id, state, inputs):
    """The number that drove the cell, with a glyph for the direction."""
    inputs = inputs or {}
    if rule_id == "stu":
        body = f"{ordinal(inputs['percentile'])} pct"
    elif rule_id == "mm_extension":
        body = f"{inputs['net_oi_pct']:+.1f}%"
    elif rule_id == "mm_flow":
        body = f"{k_contracts(inputs['change_1w'])} / {k_contracts(inputs['change_4w'])}"
    elif rule_id == "seasonal":
        body = f"{inputs['average']:+.1f} next 4w"
    elif rule_id == "energy_level":
        body = f"{inputs['vs_avg_pct']:+.1f}%"
    elif rule_id == "energy_change":
        body = f"{inputs['delta_pp']:+.1f} pp"
    elif rule_id in ("cattle_yoy", "cattle_demand"):
        body = f"{inputs['pct']:g}%"
    elif rule_id in ("canola_exports", "demand_yoy"):
        body = f"{inputs['yoy_pct']:+.1f}%"
    elif rule_id == "condition":
        body = f"{inputs['delta_pp']:+.1f} pp"
    elif rule_id == "demand_pace":
        body = f"{inputs['delta_pp']:+.1f} pp"
    else:
        body = state
    mark = GLYPH[state]
    return f"{mark} {body}".strip()


def dash(rule_id, reason, as_of=None):
    return {
        "state": None,
        "text": None,
        "rule_id": rule_id,
        "as_of": as_of,
        "inputs": {},
        "detail": reason,
        "reason": reason,
    }


def stu_of(row, world=False):
    if not row or row.get("es") is None or row.get("dc") is None:
        return None
    den = row["dc"] if world else (row["dc"] + row["ex"] if row.get("ex") is not None else None)
    if not den:
        return None
    return 100.0 * row["es"] / den


def year_rows(book, comm, country):
    node = (book or {}).get(comm, {}).get(country, {})
    out = []
    for key, row in node.items():
        if str(key).isdigit() and isinstance(row, dict):
            out.append((int(key), row))
    return sorted(out)


def fundamentals(psd, prior, comm, country, cfg, note, world=False):
    rows = year_rows(psd, comm, country)
    usable = [(y, stu_of(row, world)) for y, row in rows]
    usable = [(y, v) for y, v in usable if v is not None]
    if not usable:
        return dash("stu", "no stocks-to-use year is in the file")
    current_year, current = usable[-1]
    history = [v for _, v in usable]
    pct = page_stu_percentile(history)
    es = next(row.get("es") for y, row in rows if y == current_year)
    prev = (((prior or {}).get("data") or {}).get(comm) or {}).get(country) or {}
    prev_row = prev.get(str(current_year)) or {}
    es_prior = prev_row.get("es")
    revision = None if es is None or es_prior is None else es - es_prior
    state = stu_state(pct, revision, cfg)
    as_of = (psd.get("_meta") or {}).get("wasde_release")
    detail = (
        f"{note} Stocks/use {current:.1f}% is the {ordinal(pct)} percentile of all {len(history)} years, including this one. "
        f"Ending stocks {es:,.0f}"
        + (f" versus prior {es_prior:,.0f} ({revision:+,.0f})." if revision is not None else ". Prior ending stocks are not in the file.")
    )
    if revision is not None and state == "neutral" and (
        (pct <= cfg["stu_bull_pct"] and revision > 0) or (pct >= cfg["stu_bear_pct"] and revision < 0)
    ):
        detail += " The stocks revision disagrees with the percentile, so the cell is neutral."
    return cell(state, "stu", as_of, {
        "percentile": round(pct, 4),
        "revision": revision,
        "stu": round(current, 4),
        "ending_stocks": es,
        "ending_stocks_prior": es_prior,
        "history": [round(v, 4) for v in history],
    }, detail, "wasde", cfg)


def mm_series(cftc, code):
    node = (cftc or {}).get("codes", {}).get(code)
    if not node:
        return None, [], []
    nets, ratios = [], []
    last = None
    for row in node.get("rows") or []:
        if row[3] is None or row[4] is None:
            continue
        net = row[3] - row[4]
        nets.append(net)
        ratios.append(None if not row[1] else 100.0 * net / row[1])
        last = row[0]
    return last, nets, ratios


def mm_extension(cftc, code, cfg):
    last, nets, ratios = mm_series(cftc, code)
    need = cfg["mm_weeks"]
    window = [r for r in ratios if r is not None][-need:]
    if len(window) < need:
        return dash("mm_extension", f"managed-money history is {len(window)} weeks; the rule needs {need}", last)
    pct = percentile_at_or_below(window[-1], window)
    state = extension_state(pct, cfg)
    detail = (
        f"Managed money net {nets[-1]:+,} contracts, {window[-1]:+.1f}% of open interest. "
        f"{ordinal(pct)} percentile of the last {need} weeks. "
        + ("Extended long, read as bearish." if pct >= cfg["mm_ext_long_pct"]
           else "Extended short, read as bullish." if pct <= cfg["mm_ext_short_pct"]
           else "Inside the 15th to 85th percentiles.")
    )
    return cell(state, "mm_extension", last, {
        "percentile": round(pct, 4),
        "net": nets[-1],
        "net_oi_pct": round(window[-1], 4),
        "weeks": need,
    }, detail, "cftc", cfg)


def mm_flow(cftc, code, cfg):
    last, nets, _ratios = mm_series(cftc, code)
    if len(nets) < 5:
        return dash("mm_flow", "managed-money history is shorter than four weeks", last)
    chg1 = nets[-1] - nets[-2]
    chg4 = nets[-1] - nets[-5]
    state = flow_state(chg1, chg4)
    detail = f"Managed money net changed {chg1:+,} contracts in one week and {chg4:+,} over four weeks."
    return cell(state, "mm_flow", last, {
        "change_1w": chg1,
        "change_4w": chg4,
    }, detail, "cftc", cfg)


def seasonal_state(average, cfg):
    if average is None:
        return None
    if average >= cfg["seasonal_score_bull"]:
        return "bullish"
    if average <= cfg["seasonal_score_bear"]:
        return "bearish"
    return "neutral"


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def load_seasonals():
    """The Seasonals page keeps Peak Trading Research scores as typed JavaScript."""
    path = os.path.join(ROOT, "index.html")
    if not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8").read()
    weeks_m = re.search(r"const SEASONALS_WEEKS = (\[.*?\]);", text)
    data_m = re.search(r"const SEASONALS_DATA = (\{.*?\});", text, re.S)
    reviewed_m = re.search(r"const SEASONALS_REVIEWED = '([^']+)'", text)
    if not weeks_m or not data_m or not reviewed_m:
        return None
    weeks = json.loads(weeks_m.group(1))
    raw = re.sub(r",(\s*})", r"\1", data_m.group(1).replace("'", '"'))
    scores = json.loads(raw)
    return {"weeks": weeks, "scores": scores, "reviewed": reviewed_m.group(1)}


def current_seasonal_index(weeks, today):
    """Index of the labeled week that contains today. Labels are the Monday of that week."""
    best = None
    for i, label in enumerate(weeks):
        mon, day = label.split()
        month = MONTHS.index(mon) + 1
        for year in (today.year - 1, today.year, today.year + 1):
            try:
                start = date(year, month, int(day))
            except ValueError:
                continue
            if start <= today and (today - start).days <= 6 and (best is None or start > best[0]):
                best = (start, i)
    return None if best is None else best[1]


def seasonal_week_labels(weeks, today):
    """Five labels: the week containing today, then the next four, wrapping at year end."""
    index = current_seasonal_index(weeks, today)
    if index is None:
        return None
    return [weeks[(index + step) % len(weeks)] for step in range(5)]


def seasonal_signal(book, product, cfg):
    if not book or not product or product not in (book.get("scores") or {}):
        return dash("seasonal", "No Peak Trading Research score is typed for this market on the Seasonals page.")
    weeks = book["weeks"]
    values = book["scores"][product]
    labels = seasonal_week_labels(weeks, TODAY)
    if not labels:
        return dash("seasonal", "The current week is not in the Seasonals week list.", book.get("reviewed"))
    window = []
    for label in labels:
        i = weeks.index(label)
        if i >= len(values) or values[i] is None:
            return dash("seasonal", f"The Peak score for {label} is missing.", book.get("reviewed"))
        window.append({"week": label, "score": values[i]})
    average = sum(item["score"] for item in window) / len(window)
    state = seasonal_state(average, cfg)
    reviewed = book.get("reviewed")
    listed = ", ".join(
        f"{item['week']} {item['score']:+d}" if item["score"] != 0 else f"{item['week']} 0"
        for item in window
    )
    detail = (
        f"{listed}. Average {average:+.1f}. "
        f"Peak Trading Research seasonal, last reviewed {reviewed}."
    )
    return cell(state, "seasonal", reviewed, {
        "average": round(average, 4),
        "weeks": window,
    }, detail, None, cfg)


def export_history_years(history, commodity):
    """Marketing years present at any week. The file currently keeps one season."""
    years = set()
    for week in (history or {}).get("weeks", {}).values():
        node = week.get(commodity) or {}
        label = node.get("mkt_year")
        if label:
            years.add(label)
    return years


def demand_yoy(exports, commodity, cfg):
    total = (((exports or {}).get("commodities") or {}).get(commodity) or {}).get("total") or {}
    pct = total.get("yoy_total_commitment_pct")
    as_of = total.get("period_ending")
    if pct is None:
        return dash("demand_yoy", "Year-ago export commitment is not in the export file.", as_of)
    state = band(pct, "bearish", "bullish", -cfg["demand_pp"], cfg["demand_pp"])
    detail = f"Total export commitment {pct:+.1f}% versus a year ago. Threshold {cfg['demand_pp']:g}%."
    return cell(state, "demand_yoy", as_of, {"yoy_pct": round(float(pct), 4)}, detail, "exports", cfg)


def demand_grains(exports, history, commodity, cfg):
    years = export_history_years(history, commodity)
    as_of = None
    total = ((exports or {}).get("commodities") or {}).get(commodity, {}).get("total")
    if total:
        as_of = total.get("period_ending")
    need = cfg["demand_history_years"]
    if len(years) < need:
        return dash(
            "demand_pace",
            f"Export history covers {len(years) or 0} season{'s' if len(years) != 1 else ''}, not the {need} seasons needed for the same-week pace.",
            as_of,
        )
    return dash("demand_pace", "The five-year same-week pace is not in the export file.", as_of)


def canola_demand(cgc, cfg):
    grain = (((cgc or {}).get("headline") or {}).get("grains") or {}).get("canola") or {}
    cur, ya = grain.get("exp_cy"), grain.get("exp_ya")
    as_of = (cgc or {}).get("latest_date")
    if cur is None or not ya:
        return dash("canola_exports", "CGC crop-year exports or the year-ago figure is missing.", as_of)
    yoy = (cur / ya - 1.0) * 100.0
    state = canola_export_state(yoy, cfg)
    detail = (
        f"CGC canola exports {cur:,.1f} kt versus {ya:,.1f} kt at the same week a year ago ({yoy:+.1f}%). "
        f"Threshold {cfg['demand_pp']:g}%."
    )
    return cell(state, "canola_exports", as_of, {
        "yoy_pct": round(yoy, 4),
        "exports": cur,
        "year_ago": ya,
    }, detail, "cgc", cfg)


def in_season(kind, cfg):
    months = cfg["condition_months"].get(kind)
    if not months:
        return False
    return TODAY.month in months


def condition_signal(progress, crop_name, kind, cfg):
    if not in_season(kind, cfg):
        return dash("condition", "out of season")
    rows = [r for r in ((progress or {}).get("rows") or []) if r.get("crop") == crop_name and r.get("metric") == "condition_ge"]
    as_of = (progress or {}).get("report_date")
    if not rows:
        return dash("condition", "Good/excellent was not printed in the latest crop progress report.", as_of)
    row = rows[0]
    current = row.get("current")
    base = row.get("avg5")
    base_name = "5-year average"
    if base is None:
        base = row.get("last_year")
        base_name = "year ago"
    if current is None or base is None:
        return dash("condition", "Good/excellent has no 5-year average and no year-ago print.", as_of)
    delta = current - base
    state = condition_state(delta, cfg)
    detail = f"Good/excellent {current:g} versus {base_name} {base:g} ({delta:+.1f} pp)."
    return cell(state, "condition", as_of, {"delta_pp": round(delta, 4), "current": current, "base": base}, detail, "crop", cfg)


def iso_change(history):
    points = []
    for i in range(1, len(history)):
        d0, v0 = history[i - 1]
        d1, v1 = history[i]
        if not v0:
            continue
        day = date.fromisoformat(d1)
        iso = day.isocalendar()
        points.append((day, iso.year, iso.week, (v1 - v0) / v0 * 100.0))
    return points


def energy_level(series, cfg):
    pct = series.get("vs_avg5_pct")
    as_of = series.get("period")
    if pct is None:
        return dash("energy_level", "No 5-year average is stored for this series.", as_of)
    state = level_vs_avg_state(pct, cfg)
    basis = series.get("avg5_basis") or "5-year average"
    detail = f"Stocks {series.get('value')} versus the 5-year average {series.get('avg5')} ({pct:+.1f}%). {basis}."
    return cell(state, "energy_level", as_of, {"vs_avg_pct": pct}, detail, "energy", cfg)


def energy_change(series, cfg):
    history = series.get("history") or []
    as_of = series.get("period")
    points = iso_change(history)
    if len(points) < 20 or not as_of:
        return dash("energy_change", "Weekly history is too short to compare with the same week of the prior five years.", as_of)
    current = next((p for p in reversed(points) if p[0].isoformat() == as_of), None)
    if current is None:
        return dash("energy_change", "The latest week is not in the stock history.", as_of)
    _, year, week, now = current
    prior = []
    for y in range(year - 5, year):
        match = [p[3] for p in points if p[1] == y and p[2] == week]
        if match:
            prior.append(match[-1])
    if len(prior) < 5:
        return dash("energy_change", f"Only {len(prior)} of the five prior years have this week.", as_of)
    norm = sum(prior) / len(prior)
    delta = now - norm
    state = change_vs_norm_state(delta, cfg)
    detail = (
        f"This week's stock change is {now:+.2f}% of the prior week. "
        f"The same week of the prior five years averaged {norm:+.2f}%. Difference {delta:+.2f} pp."
    )
    return cell(state, "energy_change", as_of, {
        "delta_pp": round(delta, 4),
        "change_pct": round(now, 4),
        "norm_pct": round(norm, 4),
    }, detail, "energy", cfg)


def cattle_pct(report, key, cfg, *, demand=False, what=None):
    block = (report or {}).get(key) or {}
    pct = block.get("pct_of_year_ago")
    as_of = (report or {}).get("released")
    name = what or key.replace("_", " ")
    if pct is None:
        return dash("cattle_yoy", f"{name} percent of a year ago is not in the report.", as_of)
    low, high = cfg["cattle_yoy_low"], cfg["cattle_yoy_high"]
    if demand:
        state = band(pct, "bearish", "bullish", low, high)
        rule = "cattle_demand"
        sense = f"At or above {high} is bullish and at or below {low} is bearish, because placements are demand for feeders."
    else:
        state = yoy_pct_state(pct, low, high)
        rule = "cattle_yoy"
        sense = f"At or below {low} is bullish and at or above {high} is bearish."
    detail = (
        f"{name}: {block.get('current'):,} versus {block.get('year_ago'):,} a year ago, "
        f"{pct}% as printed. {sense}"
    )
    return cell(state, rule, as_of, {"pct": pct}, detail, "cattle", cfg)


def next_cattle_release(as_of):
    """The Cattle report after this January 1 or July 1 reference date."""
    if as_of.month == 1:
        return date(as_of.year, 7, 31)
    return date(as_of.year + 1, 1, 31)


def cattle_inventory_limit(as_of, grace):
    return next_cattle_release(as_of) + timedelta(days=grace)


def outside_feedlots_signal(cattle, cfg):
    reports = [
        row for row in (cattle or {}).get("inventory") or []
        if ((row.get("outside_feedlots") or {}).get("pct_of_year_ago") is not None)
    ]
    if not reports:
        return dash(
            "cattle_yoy",
            "The Cattle report did not print calves and other steers and heifers outside feedlots.",
        )
    latest = max(reports, key=lambda row: row.get("as_of") or "")
    block = latest["outside_feedlots"]
    as_of = parse_day(latest.get("as_of"))
    grace = cfg.get("cattle_inventory_grace_days", 10)
    if as_of and TODAY > cattle_inventory_limit(as_of, grace):
        return dash(
            "cattle_yoy",
            f"The {latest.get('as_of')} Cattle report is past 10 days after the next scheduled release.",
            as_of,
        )
    pct = block["pct_of_year_ago"]
    low, high = cfg["cattle_yoy_low"], cfg["cattle_yoy_high"]
    state = yoy_pct_state(pct, low, high)
    ya = block.get("year_ago_million")
    ya_txt = f" versus {ya} million a year ago" if ya is not None else ""
    detail = (
        f"Cattle outside feedlots, {latest.get('released') or latest.get('as_of')}: "
        f"{block.get('current_million')} million head{ya_txt}, "
        f"{pct}% of a year ago as printed in the Cattle report. "
        f"At or below {low} is bullish and at or above {high} is bearish."
    )
    return cell(state, "cattle_yoy", as_of, {"pct": pct}, detail, None, cfg)


def cutout_signal(cattle, cfg):
    cut = (cattle or {}).get("cutout") or {}
    as_of = cut.get("as_of")
    if cut.get("choice") is None:
        return dash("cutout", "Boxed beef was not in the cattle file.", as_of)
    return dash(
        "cutout",
        "Boxed beef history is a single print, so the four-week trend cannot be computed.",
        as_of,
    )


def rule_book(cfg, reviewed=None):
    c = cfg
    return [
        {"id": "stu", "text": (
            "Stocks/use percentile is the same rank as the Fundamentals page: the share of every year on that sheet, including the current year, with stocks/use at or below this year. "
            f"At or below the {c['stu_bull_pct']}rd percentile is bullish. At or above the {c['stu_bear_pct']}th is bearish. "
            "Otherwise neutral. "
            "World stocks/use is ending stocks divided by domestic use. A country uses ending stocks divided by domestic use plus exports. "
            "Canola uses the AAFC forecast stocks/use against the years on the Canada balance sheet, including the forecast year, or USDA Canada if that file is missing. "
            "If the latest ending-stocks revision moves the opposite way from the percentile, the cell becomes neutral."
        )},
        {"id": "mm_extension", "text": (
            f"Managed money net as a percent of open interest, ranked over the last {c['mm_weeks']} weeks. "
            f"At or above the {c['mm_ext_long_pct']}th percentile is extended long and reads bearish. "
            f"At or below the {c['mm_ext_short_pct']}th is extended short and reads bullish. Otherwise neutral. The cell shows the percent of open interest. "
            "Disaggregated managed money only. Leveraged Funds are not used."
        )},
        {"id": "mm_flow", "text": (
            "Change in managed money net over one week and over four weeks. Both up is bullish. Both down is bearish. "
            "A mixed pair, or a zero change, is neutral."
        )},
        {"id": "seasonal", "text": (
            "Average of the Peak Trading Research weekly scores for the current week and the next four weeks. "
            f"Scores run from −5 to +5. An average of {c['seasonal_score_bull']:g} or higher is bullish. "
            f"An average of {c['seasonal_score_bear']:g} or lower is bearish. Otherwise neutral. "
            "The same scores are reused every year, keyed by calendar week, and a late-December window continues into January. "
            "They are typed on the Seasonals page, not fetched, and they do not expire. "
            "A market with no typed score is a dash. "
            f"Peak Trading Research seasonal, last reviewed {reviewed}."
        )},
        {"id": "colour", "text": (
            "Each signal cell is coloured on its own. Bullish is green and bearish is red. Neutral has no colour. "
            "The cell shows the figure only. A missing figure is a dash with no colour. "
            "There is no row total and no section score."
        )},
        {"id": "demand_yoy", "text": (
            f"Export commitments versus a year ago, the same percent the Exports page uses. "
            f"At least +{c['demand_pp']:g}% is bullish. At least {c['demand_pp']:g}% below is bearish. Otherwise neutral. "
            "Canola uses CGC crop-year exports versus the same week a year ago, with the same band. "
            "Coffee and sugar have no series on the Exports page, so those cells are dashes."
        )},
        {"id": "canola_exports", "text": (
            f"CGC canola exports versus the same week a year ago. "
            f"At least +{c['demand_pp']:g}% is bullish and at least {c['demand_pp']:g}% below is bearish."
        )},
        {"id": "energy_level", "text": (
            f"Stocks versus the 5-year average. At least +{c['energy_vs_avg_pct']}% is bearish. "
            f"At least {c['energy_vs_avg_pct']}% below is bullish. "
            "Natural gas uses the WNGSR published percent. Petroleum uses the percent computed from weekly levels."
        )},
        {"id": "energy_change", "text": (
            f"This week's percent stock change minus the average percent change in the same week of the prior five years. "
            f"At least +{c['energy_change_vs_norm_pp']} percentage points (a heavier build or a lighter draw) is bearish. "
            f"At least {c['energy_change_vs_norm_pp']} the other way is bullish."
        )},
        {"id": "cattle_yoy", "text": (
            f"Live cattle supply is Cattle on Feed on-feed head, percent of a year ago. "
            f"Live cattle pipeline is Cattle on Feed marketings, percent of a year ago. "
            f"Feeder supply is the Cattle report total of calves under 500 pounds and other steers and heifers outside feedlots, percent of a year ago. "
            f"At or below {c['cattle_yoy_low']} is bullish and at or above {c['cattle_yoy_high']} is bearish. "
            "The percents are the ones the report prints. The semiannual figure stays current until 10 days after the next January 31 or July 31 release."
        )},
        {"id": "cattle_demand", "text": (
            f"Feeder pipeline is Cattle on Feed placements, percent of a year ago, scored as demand for feeder cattle. "
            f"At or above {c['cattle_yoy_high']} is bullish and at or below {c['cattle_yoy_low']} is bearish."
        )},
        {"id": "cutout", "text": (
            "Choice boxed beef from the USDA AMS boxed-beef report is an official print, not a futures price. "
            "The file has a single print, so a four-week trend cannot be scored and the column is omitted. The figure stays in Key figures."
        )},
        {"id": "staleness", "text": (
            "A cell whose as-of date is older than its cadence is a dash. Cadences, in days: "
            + ", ".join(f"{k} {v}" for k, v in c["cadence_days"].items()) + "."
        )},
    ]


def ordinal(n):
    n = int(round(n))
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def row(label, signals, figures, page=None, comm=None, cfg=None):
    del cfg
    return {
        "label": label,
        "signals": signals,
        "figures": figures,
        "page": page,
        "comm": comm,
    }


def canola_sheet_years(crop):
    """The crop years printed on the Canada canola balance, including the forecast."""
    years = (crop or {}).get("years") or {}
    forecast = (crop or {}).get("forecast_year")
    stat = sorted(key for key, row in years.items() if row.get("src") == "StatsCan" and key != forecast)
    estimates = [
        key for key in ((crop or {}).get("aafc_years") or [])
        if key != forecast and (years.get(key) or {}).get("src") == "AAFC"
    ]
    return [key for key in [*stat[-5:], *estimates, forecast] if (years.get(key) or {}).get("su") is not None]


def canola_fundamentals(sd, psd, prior, cfg):
    crop = (((sd or {}).get("crops") or {}).get("canola") or {})
    years = crop.get("years") or {}
    forecast = crop.get("forecast_year")
    sheet = years.get(forecast) if forecast else None
    cols = canola_sheet_years(crop)
    if sheet and sheet.get("su") is not None and cols:
        history = [years[key]["su"] for key in cols]
        current = history[-1]
        pct = page_stu_percentile(history)
        es = sheet.get("end")
        es_prior = (crop.get("prior") or {}).get("end")
        revision = None if es is None or es_prior is None else es - es_prior
        state = stu_state(pct, revision, cfg)
        detail = (
            f"AAFC canola stocks/use {current:.1f}% is the {ordinal(pct)} percentile of the {len(history)} years on the Canada sheet, including this one. "
            f"Ending stocks {es:,.0f}"
            + (f" versus the prior report {es_prior:,.0f} ({revision:+,.0f})." if revision is not None else ".")
        )
        return cell(state, "stu", (sd.get("aafc") or {}).get("date"), {
            "percentile": round(pct, 4),
            "revision": revision,
            "stu": round(current, 4),
            "ending_stocks": es,
            "ending_stocks_prior": es_prior,
            "history": [round(v, 4) for v in history],
        }, detail, "aafc", cfg)
    return fundamentals(psd, prior, "Rapeseed/Canola", "Canada", cfg, "USDA Canada stocks/use, because the AAFC sheet is missing.")


def build(cfg=None):
    cfg = cfg or load_config()
    psd = load_json("psd_data.json") or {}
    prior = psd.get("_prior")
    cftc = load_json("cftc_data.json")
    exports = load_json("export_sales.json")
    history = load_json("export_sales_history.json")
    energy = load_json("energy.json") or {}
    cattle = load_json("cattle.json") or {}
    progress = load_json("us.json")
    cgc = load_json("cgc.json")
    sd = load_json("sd.json")
    series = {s["key"]: s for s in energy.get("series") or []}
    feed = (cattle.get("on_feed") or [None])[-1]
    seasonals = load_seasonals()

    def grain(label, comm, country, cftc_code, fas, condition_kind, crop_name, fund_note, peak):
        fund = fundamentals(psd, prior, comm, country, cfg, fund_note)
        demand = demand_yoy(exports, fas, cfg) if fas else dash("demand_yoy", "No export series is wired for this row.")
        if fas is None and label == "Canola":
            demand = canola_demand(cgc, cfg)
        sigs = {
            "stu": fund,
            "mm_extension": mm_extension(cftc, cftc_code, cfg),
            "mm_flow": mm_flow(cftc, cftc_code, cfg),
            "demand": demand,
            "seasonal": seasonal_signal(seasonals, peak, cfg),
        }
        figs = []
        if fund["inputs"].get("stu") is not None:
            figs.append({"label": "S/U", "value": f"{fund['inputs']['stu']:.1f}%"})
        if fund["inputs"].get("ending_stocks") is not None:
            figs.append({"label": "Ending stocks", "value": f"{fund['inputs']['ending_stocks']:,.0f}"})
        if fund["inputs"].get("revision") is not None:
            figs.append({"label": "Stocks revision", "value": f"{fund['inputs']['revision']:+,.0f}"})
        return row(label, sigs, figs, "usda", comm, cfg)

    grains = [
        grain("Corn", "Corn", "United States", "002602", "CORN - UNMILLED", "corn", "Corn", "US corn stocks/use.", "Corn"),
        grain("Wheat (Chicago SRW)", "Wheat", "United States", "001602", "ALL WHEAT", "wheat_winter", "Wheat, Winter", "US all-wheat stocks/use.", "Chicago Wheat"),
        grain("Wheat (KC HRW)", "Wheat", "United States", "001612", "ALL WHEAT", "wheat_winter", "Wheat, Winter", "US all-wheat stocks/use. There is no separate HRW balance in this file.", "Kansas Wheat"),
        grain("Wheat (MGEX)", "Wheat", "United States", "001626", "ALL WHEAT", "wheat_spring", "Wheat, Spring", "US all-wheat stocks/use. There is no separate spring-wheat balance in this file.", "Spring Wheat"),
    ]
    oilseeds = [
        grain("Soybeans", "Soybeans", "United States", "005602", "SOYBEANS", "soybeans", "Soybeans", "US soybean stocks/use.", "Soybeans"),
    ]
    canola_fund = canola_fundamentals(sd, psd, prior, cfg)
    canola_sigs = {
        "stu": canola_fund,
        "mm_extension": mm_extension(cftc, "135731", cfg),
        "mm_flow": mm_flow(cftc, "135731", cfg),
        "demand": canola_demand(cgc, cfg),
        "seasonal": seasonal_signal(seasonals, "Canola Seed", cfg),
    }
    canola_figs = []
    if canola_fund["inputs"].get("stu") is not None:
        canola_figs.append({"label": "S/U", "value": f"{canola_fund['inputs']['stu']:.1f}%"})
    if canola_fund["inputs"].get("ending_stocks") is not None:
        canola_figs.append({"label": "Ending stocks", "value": f"{canola_fund['inputs']['ending_stocks']:,.0f}"})
    if canola_fund["inputs"].get("revision") is not None:
        canola_figs.append({"label": "Stocks revision", "value": f"{canola_fund['inputs']['revision']:+,.0f}"})
    oilseeds.append(row("Canola", canola_sigs, canola_figs, "usda", "Rapeseed/Canola", cfg))
    oilseeds.append(grain("Soybean meal", "Soybean Meal", "United States", "026603", "SOYBEAN CAKE AND MEAL", None, None, "US soybean meal stocks/use.", "Soybean Meal"))
    oilseeds.append(grain("Soybean oil", "Soybean Oil", "United States", "007601", "SOYBEAN OIL", None, None, "US soybean oil stocks/use.", "Soybean Oil"))

    def energy_row(label, key, code):
        ser = series.get(key) or {}
        level = energy_level(ser, cfg)
        change = energy_change(ser, cfg)
        sigs = {
            "energy_level": level,
            "energy_change": change,
            "mm_extension": mm_extension(cftc, code, cfg),
            "mm_flow": mm_flow(cftc, code, cfg),
        }
        figs = []
        if ser.get("value") is not None:
            figs.append({"label": "Stocks", "value": f"{ser['value']:,}"})
        if ser.get("change") is not None:
            figs.append({"label": "Week change", "value": f"{ser['change']:+,}"})
        if ser.get("vs_avg5_pct") is not None:
            figs.append({"label": "Vs 5-yr", "value": f"{ser['vs_avg5_pct']:+.1f}%"})
        return row(label, sigs, figs, "usda", "Energy", cfg)

    soft_specs = [
        ("Coffee", "Coffee", "World", "083731", None, "Arabica Coffee", "World coffee stocks/use."),
        ("Sugar", "Sugar", "World", "080732", None, "Sugar No. 11", "World sugar stocks/use."),
        ("Cotton", "Cotton", "World", "033661", "ALL UPLAND COTTON", "Cotton", "World cotton stocks/use."),
        ("Cocoa", "Cocoa", "World", "073732", None, "NY Cocoa", "World cocoa stocks/use."),
    ]
    softs = []
    for label, comm, country, code, fas, peak, note in soft_specs:
        if comm not in (psd or {}):
            continue
        fund = fundamentals(psd, prior, comm, country, cfg, note, world=(country == "World"))
        sigs = {
            "stu": fund,
            "demand": demand_yoy(exports, fas, cfg) if fas else dash("demand_yoy", "No export series is in the export file for this market."),
            "seasonal": seasonal_signal(seasonals, peak, cfg),
            "mm_extension": mm_extension(cftc, code, cfg),
            "mm_flow": mm_flow(cftc, code, cfg),
        }
        softs.append(row(label, sigs, [], "usda", comm, cfg))

    energy_rows = [
        energy_row("Crude (WTI)", "crude_stocks", "067651"),
        energy_row("Gasoline (RBOB)", "gas_stocks", "111659"),
        energy_row("Distillate (Heating oil)", "dist_stocks", "022651"),
        energy_row("Natural gas", "ng_storage", "023651"),
    ]
    on_feed = cattle_pct(feed, "on_feed", cfg, what="Cattle on feed")
    marketings = cattle_pct(feed, "marketings", cfg, what="Marketings")
    placements = cattle_pct(feed, "placements", cfg, demand=True, what="Placements")
    outside = outside_feedlots_signal(cattle, cfg)
    on_feed["caption"] = "On feed"
    marketings["caption"] = "Marketings"
    outside["caption"] = "Outside feedlots"
    placements["caption"] = "Placements"
    cut = cutout_signal(cattle, cfg)

    def cattle_row(label, supply, pipeline, code, peak):
        sigs = {
            "supply": supply,
            "pipeline": pipeline,
            "mm_extension": mm_extension(cftc, code, cfg),
            "mm_flow": mm_flow(cftc, code, cfg),
            "seasonal": seasonal_signal(seasonals, peak, cfg),
        }
        return row(label, sigs, [], "usda", "Cattle", cfg)

    cattle_rows = [
        cattle_row("Live cattle", on_feed, marketings, "057642", "Cattle"),
        cattle_row("Feeder cattle", outside, placements, "061641", "Feeder Cattle"),
    ]
    cattle_figs = []
    if feed and feed.get("on_feed"):
        cattle_figs.append({"label": "On feed", "value": f"{feed['on_feed']['pct_of_year_ago']}% of yr ago"})
    if feed and feed.get("marketings"):
        cattle_figs.append({"label": "Marketings", "value": f"{feed['marketings']['pct_of_year_ago']}% of yr ago"})
    if feed and feed.get("placements"):
        cattle_figs.append({"label": "Placements", "value": f"{feed['placements']['pct_of_year_ago']}% of yr ago"})
    if outside.get("inputs", {}).get("pct") is not None:
        cattle_figs.append({"label": "Outside feedlots", "value": f"{outside['inputs']['pct']}% of yr ago"})
    choice = (cattle.get("cutout") or {}).get("choice")
    if choice is not None:
        cattle_figs.append({"label": "Choice cutout", "value": f"{choice:.2f}"})

    sections = [
        {
            "id": "grains",
            "title": "Grains",
            "basis": "Fundamentals out of 3 (stocks/use, demand, seasonal). Managed money out of 2. A dash is left out of that row.",
            "groups": [
                {"label": "Fundamentals", "ids": ["stu", "demand", "seasonal"]},
                {"label": "Managed money", "ids": ["mm_extension", "mm_flow"]},
            ],
            "columns": [
                {"id": "stu", "label": "Stocks/use"},
                {"id": "demand", "label": "Demand"},
                {"id": "seasonal", "label": "Seasonal"},
                {"id": "mm_extension", "label": "Extended"},
                {"id": "mm_flow", "label": "Money flow"},
            ],
            "rows": grains,
            "figures": [],
        },
        {
            "id": "oilseeds",
            "title": "Oilseeds",
            "basis": "Fundamentals out of 3 (stocks/use, demand, seasonal). Managed money out of 2. A dash is left out of that row.",
            "groups": [
                {"label": "Fundamentals", "ids": ["stu", "demand", "seasonal"]},
                {"label": "Managed money", "ids": ["mm_extension", "mm_flow"]},
            ],
            "columns": [
                {"id": "stu", "label": "Stocks/use"},
                {"id": "demand", "label": "Demand"},
                {"id": "seasonal", "label": "Seasonal"},
                {"id": "mm_extension", "label": "Extended"},
                {"id": "mm_flow", "label": "Money flow"},
            ],
            "rows": oilseeds,
            "figures": [],
        },
        {
            "id": "softs",
            "title": "Softs",
            "basis": "Fundamentals out of 3 (stocks/use, demand, seasonal). Managed money out of 2. A dash is left out of that row.",
            "groups": [
                {"label": "Fundamentals", "ids": ["stu", "demand", "seasonal"]},
                {"label": "Managed money", "ids": ["mm_extension", "mm_flow"]},
            ],
            "columns": [
                {"id": "stu", "label": "Stocks/use"},
                {"id": "demand", "label": "Demand"},
                {"id": "seasonal", "label": "Seasonal"},
                {"id": "mm_extension", "label": "Extended"},
                {"id": "mm_flow", "label": "Money flow"},
            ],
            "rows": softs,
            "figures": [],
        },
        {
            "id": "energy",
            "title": "Energy",
            "basis": "Fundamentals out of 2 (stocks vs 5-yr and week vs norm). There is no seasonal column. Managed money out of 2.",
            "groups": [
                {"label": "Fundamentals", "ids": ["energy_level", "energy_change"]},
                {"label": "Managed money", "ids": ["mm_extension", "mm_flow"]},
            ],
            "columns": [
                {"id": "energy_level", "label": "Stocks vs 5-yr"},
                {"id": "energy_change", "label": "Week vs norm"},
                {"id": "mm_extension", "label": "Extended"},
                {"id": "mm_flow", "label": "Money flow"},
            ],
            "rows": energy_rows,
            "figures": [],
        },
        {
            "id": "cattle",
            "title": "Cattle",
            "basis": "Live supply is on feed and pipeline is marketings. Feeder supply is cattle outside feedlots and pipeline is placements. Seasonal is Peak. Managed money is out of 2.",
            "groups": [
                {"label": "Fundamentals", "ids": ["supply", "pipeline", "seasonal"]},
                {"label": "Managed money", "ids": ["mm_extension", "mm_flow"]},
            ],
            "columns": [
                {"id": "supply", "label": "Supply", "tip": "Live cattle: Cattle on Feed, on feed, percent of a year ago. Feeder cattle: Cattle report, calves and other steers and heifers outside feedlots, percent of a year ago."},
                {"id": "pipeline", "label": "Pipeline", "tip": "Live cattle: Cattle on Feed marketings, percent of a year ago. At or below 98 is bullish. Feeder cattle: placements, percent of a year ago, scored as feeder demand. At or above 102 is bullish."},
                {"id": "seasonal", "label": "Seasonal", "tip": "Peak Trading Research seasonal for this cattle contract."},
                {"id": "mm_extension", "label": "Extended"},
                {"id": "mm_flow", "label": "Money flow"},
            ],
            "rows": cattle_rows,
            "figures": cattle_figs,
        },
    ]
    return {
        "generated_at": datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "config": cfg,
        "rules": rule_book(cfg, (seasonals or {}).get("reviewed")),
        "freshness": feed_freshness(cfg, psd, cftc, exports, energy, cattle, cgc, sd, load_json("weather_data.json")),
        "sections": sections,
    }


def feed_freshness(cfg, psd, cftc, exports, energy, cattle, cgc, sd, weather):
    """As-of is the report date. last_run is when the fetch last succeeded. Stale is decided in the browser."""
    rows = []

    def add(feed, as_of, cadence, ran):
        day = parse_day(as_of)
        stamp = str(ran)[:16].replace("T", " ") if ran else None
        rows.append({
            "feed": feed,
            "as_of": day.isoformat() if day else None,
            "last_run": stamp,
            "cadence_days": cadence,
        })

    meta = (psd or {}).get("_meta") or {}
    add("WASDE", meta.get("wasde_release"), cfg["cadence_days"]["wasde"], meta.get("fetched_at"))
    last_cftc = None
    for node in ((cftc or {}).get("codes") or {}).values():
        if node.get("rows"):
            last_cftc = node["rows"][-1][0]
            break
    add("CFTC", last_cftc, cfg["cadence_days"]["cftc"], ((cftc or {}).get("_meta") or {}).get("fetched_at"))
    corn = (((exports or {}).get("commodities") or {}).get("CORN - UNMILLED") or {}).get("total") or {}
    add("Export sales", corn.get("period_ending"), cfg["cadence_days"]["exports"], ((exports or {}).get("_meta") or {}).get("fetched_at"))
    series = (energy or {}).get("series") or []
    add("EIA", series[0].get("period") if series else None, cfg["cadence_days"]["energy"], (energy or {}).get("generated_at"))
    latest_feed = ((cattle or {}).get("on_feed") or [None])[-1] or {}
    add("Cattle on feed", latest_feed.get("released"), cfg["cadence_days"]["cattle"], (cattle or {}).get("updated"))
    inventory = [
        row for row in (cattle or {}).get("inventory") or []
        if (row.get("outside_feedlots") or {}).get("pct_of_year_ago") is not None
    ]
    latest_inv = max(inventory, key=lambda row: row.get("as_of") or "") if inventory else {}
    inv_as_of = parse_day(latest_inv.get("as_of")) if latest_inv else None
    inv_cadence = None
    if inv_as_of:
        inv_cadence = (cattle_inventory_limit(inv_as_of, cfg.get("cattle_inventory_grace_days", 10)) - TODAY).days + age_days(inv_as_of)
    add("Cattle inventory", latest_inv.get("as_of"), inv_cadence, (cattle or {}).get("updated"))
    add("CGC", (cgc or {}).get("latest_date"), cfg["cadence_days"]["cgc"], (cgc or {}).get("updated"))
    add("AAFC", ((sd or {}).get("aafc") or {}).get("date"), cfg["cadence_days"]["aafc"], (sd or {}).get("updated"))
    wx = (weather or {}).get("_meta") or {}
    add("Weather", wx.get("fetched_at"), cfg["cadence_days"]["weather"], wx.get("fetched_at"))
    add("Seasonal", (load_seasonals() or {}).get("reviewed"), None, None)
    return rows


def main():
    doc = build()
    os.makedirs(DATA, exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    for section in doc["sections"]:
        print(section["title"])
        for item in section["rows"]:
            bits = []
            for key, sig in item["signals"].items():
                bits.append(f"{key}={sig['text'] or '—'}")
            print(" ", item["label"], " ".join(bits))


if __name__ == "__main__":
    main()

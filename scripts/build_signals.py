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
from datetime import date, datetime

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
    """Share of sample values at or below `value`, in percent. Sample does not include value."""
    if value is None or not sample:
        return None
    return 100.0 * sum(1 for x in sample if x <= value) / len(sample)


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
    # A crop worse than the comparison is bullish for price.
    return band(delta_pp, "bullish", "bearish", -cfg["condition_pp"], cfg["condition_pp"])


def demand_pace_state(delta_pp, cfg):
    return band(delta_pp, "bearish", "bullish", -cfg["demand_pp"], cfg["demand_pp"])


def canola_export_state(yoy_pct, cfg):
    return band(yoy_pct, "bearish", "bullish", -cfg["canola_export_yoy_pct"], cfg["canola_export_yoy_pct"])


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
    if rule_id == "condition":
        return condition_state(inputs.get("delta_pp"), cfg)
    if rule_id == "demand_pace":
        return demand_pace_state(inputs.get("delta_pp"), cfg)
    if rule_id == "canola_exports":
        return canola_export_state(inputs.get("yoy_pct"), cfg)
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
    limit = cfg["cadence_days"][cadence_key]
    old = age_days(day)
    if old is None or old > limit:
        rec["state"] = None
        rec["text"] = None
        rec["reason"] = f"stale: {as_text or 'undated'} is older than {limit} days"
        return rec
    rec["text"] = figure_text(rule_id, state, inputs)
    return rec


GLYPH = {"bullish": "▲", "bearish": "▼", "neutral": "▬"}


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
        rank = ordinal(inputs["percentile"])
        if state == "bearish":
            body = f"Ext long {rank}"
        elif state == "bullish":
            body = f"Ext short {rank}"
        else:
            body = f"{rank} pct"
    elif rule_id == "mm_flow":
        body = f"{k_contracts(inputs['change_1w'])} / {k_contracts(inputs['change_4w'])}"
    elif rule_id == "seasonal":
        body = f"{inputs['average']:+.1f} next 4w"
    elif rule_id == "energy_level":
        body = f"{inputs['vs_avg_pct']:+.1f}%"
    elif rule_id == "energy_change":
        body = f"{inputs['delta_pp']:+.1f} pp"
    elif rule_id == "cattle_yoy":
        body = f"{inputs['pct']:g}%"
    elif rule_id == "canola_exports":
        body = f"{inputs['yoy_pct']:+.0f}%"
    elif rule_id == "condition":
        body = f"{inputs['delta_pp']:+.1f} pp"
    elif rule_id == "demand_pace":
        body = f"{inputs['delta_pp']:+.1f} pp"
    else:
        body = state
    return f"{GLYPH[state]} {body}"


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


def score_label(score, cfg):
    if score >= cfg["score_supportive"]:
        return "Supportive"
    if score <= cfg["score_bearish"]:
        return "Bearish"
    return "Neutral"


def score_of(signals, cfg):
    total = 0
    scored = 0
    for sig in signals.values():
        state = sig.get("state")
        if state == "bullish":
            total += 1
            scored += 1
        elif state == "bearish":
            total -= 1
            scored += 1
        elif state == "neutral":
            scored += 1
    return {"score": total, "scored": scored, "label": score_label(total, cfg)}


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


def fundamentals(psd, prior, comm, country, cfg, note):
    rows = year_rows(psd, comm, country)
    usable = [(y, stu_of(row, False)) for y, row in rows]
    usable = [(y, v) for y, v in usable if v is not None]
    if len(usable) < cfg["stu_history_years"] + 1:
        return dash("stu", f"only {len(usable)} stocks-to-use years; the rule needs {cfg['stu_history_years']} prior years")
    current_year, current = usable[-1]
    history = [v for _, v in usable[-(cfg["stu_history_years"] + 1):-1]]
    if len(history) < cfg["stu_history_years"]:
        return dash("stu", "the prior window is short")
    pct = percentile_at_or_below(current, history)
    es = next(row.get("es") for y, row in rows if y == current_year)
    prev = (((prior or {}).get("data") or {}).get(comm) or {}).get(country) or {}
    prev_row = prev.get(str(current_year)) or {}
    es_prior = prev_row.get("es")
    revision = None if es is None or es_prior is None else es - es_prior
    state = stu_state(pct, revision, cfg)
    as_of = (psd.get("_meta") or {}).get("wasde_release")
    detail = (
        f"{note} Stocks/use {current:.1f}% is the {ordinal(pct)} percentile of the prior {len(history)} years. "
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
        return None, []
    nets = []
    last = None
    for row in node.get("rows") or []:
        if row[3] is None or row[4] is None:
            continue
        nets.append(row[3] - row[4])
        last = row[0]
    return last, nets


def mm_extension(cftc, code, cfg):
    last, nets = mm_series(cftc, code)
    need = cfg["mm_weeks"]
    if len(nets) < need:
        return dash("mm_extension", f"managed-money history is {len(nets)} weeks; the rule needs {need}", last)
    window = nets[-need:]
    pct = percentile_at_or_below(window[-1], window)
    # The current week is inside the window, so the percentile includes it.
    state = extension_state(pct, cfg)
    detail = (
        f"Managed money net {window[-1]:+,} contracts. "
        f"{ordinal(pct)} percentile of the last {need} weeks. "
        + ("Extended long, read as bearish." if state == "bearish" and pct >= cfg["mm_ext_long_pct"]
           else "Extended short, read as bullish." if state == "bullish" and pct <= cfg["mm_ext_short_pct"]
           else "Inside the 15th to 85th percentiles.")
    )
    return cell(state, "mm_extension", last, {
        "percentile": round(pct, 4),
        "net": window[-1],
        "weeks": need,
    }, detail, "cftc", cfg)


def mm_flow(cftc, code, cfg):
    last, nets = mm_series(cftc, code)
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


def seasonal_signal(book, product, cfg):
    if not book or not product or product not in (book.get("scores") or {}):
        return dash("seasonal", "No Peak Trading Research score is typed for this market on the Seasonals page.")
    weeks = book["weeks"]
    values = book["scores"][product]
    index = current_seasonal_index(weeks, TODAY)
    if index is None:
        return dash("seasonal", "The current week is not in the Seasonals week list.", book.get("reviewed"))
    window = []
    for step in range(5):
        i = (index + step) % len(weeks)
        if i >= len(values) or values[i] is None:
            return dash("seasonal", f"The Peak score for {weeks[i]} is missing.", book.get("reviewed"))
        window.append({"week": weeks[i], "score": values[i]})
    average = sum(item["score"] for item in window) / len(window)
    state = seasonal_state(average, cfg)
    listed = ", ".join(
        f"{item['week']} {item['score']:+d}" if item["score"] != 0 else f"{item['week']} 0"
        for item in window
    )
    detail = (
        f"{listed}. Average {average:+.1f}. "
        "Source: Peak Trading Research seasonal."
    )
    return cell(state, "seasonal", book.get("reviewed"), {
        "average": round(average, 4),
        "weeks": window,
    }, detail, "seasonal", cfg)


def export_history_years(history, commodity):
    """Marketing years present at any week. The file currently keeps one season."""
    years = set()
    for week in (history or {}).get("weeks", {}).values():
        node = week.get(commodity) or {}
        label = node.get("mkt_year")
        if label:
            years.add(label)
    return years


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
        f"Threshold {cfg['canola_export_yoy_pct']:g}%."
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


def cattle_pct(report, key, cfg):
    block = (report or {}).get(key) or {}
    pct = block.get("pct_of_year_ago")
    as_of = (report or {}).get("released")
    if pct is None:
        return dash("cattle_yoy", f"{key.replace('_', ' ')} percent of a year ago is not in the report.", as_of)
    state = yoy_pct_state(pct, cfg["cattle_yoy_low"], cfg["cattle_yoy_high"])
    detail = (
        f"{key.replace('_', ' ').capitalize()} {block.get('current'):,} versus {block.get('year_ago'):,} a year ago, "
        f"{pct}% as printed. Thresholds {cfg['cattle_yoy_low']} and {cfg['cattle_yoy_high']}."
    )
    return cell(state, "cattle_yoy", as_of, {"pct": pct}, detail, "cattle", cfg)


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


def rule_book(cfg):
    c = cfg
    return [
        {"id": "stu", "text": (
            f"Stocks/use percentile versus the prior {c['stu_history_years']} marketing years. "
            f"At or below the {c['stu_bull_pct']}rd percentile is bullish. At or above the {c['stu_bear_pct']}th is bearish. "
            "Otherwise neutral. Percentile is the share of those prior years at or below the current stocks/use. "
            "US corn, soybeans, wheat, soybean meal and soybean oil use ending stocks divided by domestic use plus exports. "
            "Canola uses the AAFC forecast stocks/use, or USDA Canada if that file is missing. "
            "If the latest ending-stocks revision moves the opposite way from the percentile, the cell becomes neutral."
        )},
        {"id": "mm_extension", "text": (
            f"Managed money net (long minus short) as a percentile of the last {c['mm_weeks']} weeks, current week included. "
            f"At or above the {c['mm_ext_long_pct']}th percentile is extended long and the cell reads bearish. "
            f"At or below the {c['mm_ext_short_pct']}th is extended short and the cell reads bullish. Otherwise neutral. "
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
            "The scores are typed on the Seasonals page. They are not fetched. "
            "A market with no typed score is a dash. The as-of date is the day those scores were last reviewed."
        )},
        {"id": "score", "text": (
            "A bullish cell is +1, a bearish cell is −1, and a neutral cell is 0. Dashes are left out. "
            f"A row or section total of {c['score_supportive']:+d} or higher is Supportive. "
            f"{c['score_bearish']:+d} or lower is Bearish. Anything between is Neutral."
        )},
        {"id": "demand_pace", "text": (
            f"US export commitments as a percent of the USDA export forecast, minus the {c['demand_history_years']}-year average of that percent at the same week. "
            f"At least +{c['demand_pp']} percentage points ahead is bullish. At least {c['demand_pp']} behind is bearish. "
            "The saved export history does not cover those earlier seasons, so the cell is a dash. "
            f"Canola uses CGC crop-year exports versus the same week a year ago. "
            f"At least +{c['canola_export_yoy_pct']:g}% is bullish and at least {c['canola_export_yoy_pct']:g}% behind is bearish."
        )},
        {"id": "condition", "text": (
            f"NASS good/excellent minus the printed 5-year average, or minus year ago when the average is not printed. "
            f"At least {c['condition_pp']} points below is bullish. At least {c['condition_pp']} points above is bearish. "
            "Outside the months listed in the config the cell says out of season. Meal and oil have no condition series."
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
            f"Cattle on Feed printed percent of a year ago. At or below {c['cattle_yoy_low']} is bullish. "
            f"At or above {c['cattle_yoy_high']} is bearish. The same thresholds are used for placements. "
            "Both cattle rows use this one report."
        )},
        {"id": "cutout", "text": (
            f"Choice boxed beef over four weeks. Up more than {c['cutout_flat_pct']}% is bullish, down more than that is bearish, "
            "inside the band is neutral. The cattle file has one print, so the cell is a dash. "
            "Slaughter pace is omitted because the AMS report does not print a year-ago head count."
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
    return {
        "label": label,
        "signals": signals,
        "score": score_of(signals, cfg) if cfg else None,
        "figures": figures,
        "page": page,
        "comm": comm,
    }


def canola_fundamentals(sd, psd, prior, cfg):
    crop = (((sd or {}).get("crops") or {}).get("canola") or {})
    years = crop.get("years") or {}
    forecast = crop.get("forecast_year")
    sheet = years.get(forecast) if forecast else None
    if sheet and sheet.get("su") is not None:
        history = []
        for key in sorted(years):
            if key == forecast:
                continue
            if years[key].get("src") == "StatsCan" and years[key].get("su") is not None:
                history.append(years[key]["su"])
        history = history[-cfg["stu_history_years"]:]
        if len(history) < cfg["stu_history_years"]:
            return dash("stu", f"StatsCan stocks/use history has {len(history)} years, not {cfg['stu_history_years']}.")
        current = sheet["su"]
        pct = percentile_at_or_below(current, history)
        es = sheet.get("end")
        es_prior = (crop.get("prior") or {}).get("end")
        revision = None if es is None or es_prior is None else es - es_prior
        state = stu_state(pct, revision, cfg)
        detail = (
            f"AAFC canola stocks/use {current:.1f}% is the {ordinal(pct)} percentile of the prior {len(history)} StatsCan years. "
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
        demand = demand_grains(exports, history, fas, cfg) if fas else dash("demand_pace", "No export series is wired for this row.")
        if fas is None and label == "Canola":
            demand = canola_demand(cgc, cfg)
        cond = condition_signal(progress, crop_name, condition_kind, cfg) if condition_kind else dash("condition", "not a crop-condition series")
        sigs = {
            "stu": fund,
            "mm_extension": mm_extension(cftc, cftc_code, cfg),
            "mm_flow": mm_flow(cftc, cftc_code, cfg),
            "seasonal": seasonal_signal(seasonals, peak, cfg),
            "demand": demand,
            "condition": cond,
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
        grain("Soybeans", "Soybeans", "United States", "005602", "SOYBEANS", "soybeans", "Soybeans", "US soybean stocks/use.", "Soybeans"),
        grain("Wheat (Chicago SRW)", "Wheat", "United States", "001602", "ALL WHEAT", "wheat_winter", "Wheat, Winter", "US all-wheat stocks/use.", "Chicago Wheat"),
        grain("Wheat (KC HRW)", "Wheat", "United States", "001612", "ALL WHEAT", "wheat_winter", "Wheat, Winter", "US all-wheat stocks/use. There is no separate HRW balance in this file.", "Kansas Wheat"),
        grain("Wheat (MGEX)", "Wheat", "United States", "001626", "ALL WHEAT", "wheat_spring", "Wheat, Spring", "US all-wheat stocks/use. There is no separate spring-wheat balance in this file.", "Spring Wheat"),
    ]
    canola_fund = canola_fundamentals(sd, psd, prior, cfg)
    canola_sigs = {
        "stu": canola_fund,
        "mm_extension": mm_extension(cftc, "135731", cfg),
        "mm_flow": mm_flow(cftc, "135731", cfg),
        "seasonal": seasonal_signal(seasonals, "Canola Seed", cfg),
        "demand": canola_demand(cgc, cfg),
        "condition": dash("condition", "No canola condition series is in the crop progress file."),
    }
    canola_figs = []
    if canola_fund["inputs"].get("stu") is not None:
        canola_figs.append({"label": "S/U", "value": f"{canola_fund['inputs']['stu']:.1f}%"})
    if canola_fund["inputs"].get("ending_stocks") is not None:
        canola_figs.append({"label": "Ending stocks", "value": f"{canola_fund['inputs']['ending_stocks']:,.0f}"})
    if canola_fund["inputs"].get("revision") is not None:
        canola_figs.append({"label": "Stocks revision", "value": f"{canola_fund['inputs']['revision']:+,.0f}"})
    grains.append(row("Canola", canola_sigs, canola_figs, "usda", "Rapeseed/Canola", cfg))
    grains.append(grain("Soybean meal", "Soybean Meal", "United States", "026603", "SOYBEAN CAKE AND MEAL", None, None, "US soybean meal stocks/use.", "Soybean Meal"))
    grains.append(grain("Soybean oil", "Soybean Oil", "United States", "007601", "SOYBEAN OIL", None, None, "US soybean oil stocks/use.", "Soybean Oil"))

    def energy_row(label, key, code):
        ser = series.get(key) or {}
        level = energy_level(ser, cfg)
        change = energy_change(ser, cfg)
        sigs = {
            "energy_level": level,
            "energy_change": change,
            "mm_extension": mm_extension(cftc, code, cfg),
            "mm_flow": mm_flow(cftc, code, cfg),
            "seasonal": seasonal_signal(seasonals, None, cfg),
        }
        figs = []
        if ser.get("value") is not None:
            figs.append({"label": "Stocks", "value": f"{ser['value']:,}"})
        if ser.get("change") is not None:
            figs.append({"label": "Week change", "value": f"{ser['change']:+,}"})
        if ser.get("vs_avg5_pct") is not None:
            figs.append({"label": "Vs 5-yr", "value": f"{ser['vs_avg5_pct']:+.1f}%"})
        return row(label, sigs, figs, "energy", key, cfg)

    energy_rows = [
        energy_row("Crude (WTI)", "crude_stocks", "067651"),
        energy_row("Gasoline (RBOB)", "gas_stocks", "111659"),
        energy_row("Distillate (Heating oil)", "dist_stocks", "022651"),
        energy_row("Natural gas", "ng_storage", "023651"),
    ]
    on_feed = cattle_pct(feed, "on_feed", cfg)
    placements = cattle_pct(feed, "placements", cfg)
    cut = cutout_signal(cattle, cfg)

    def cattle_row(label, code, peak):
        sigs = {
            "on_feed": on_feed,
            "placements": placements,
            "cutout": cut,
            "mm_extension": mm_extension(cftc, code, cfg),
            "mm_flow": mm_flow(cftc, code, cfg),
            "seasonal": seasonal_signal(seasonals, peak, cfg),
        }
        return row(label, sigs, [], "cattle", None, cfg)

    cattle_rows = [
        cattle_row("Live cattle", "057642", "Cattle"),
        cattle_row("Feeder cattle", "061641", "Feeder Cattle"),
    ]
    cattle_figs = []
    if feed and feed.get("on_feed"):
        cattle_figs.append({"label": "On feed", "value": f"{feed['on_feed']['pct_of_year_ago']}% of yr ago"})
    if feed and feed.get("placements"):
        cattle_figs.append({"label": "Placements", "value": f"{feed['placements']['pct_of_year_ago']}% of yr ago"})
    choice = (cattle.get("cutout") or {}).get("choice")
    if choice is not None:
        cattle_figs.append({"label": "Choice cutout", "value": f"{choice:.2f}"})

    sections = [
        {
            "id": "grains",
            "title": "Grains & Oilseeds",
            "columns": [
                {"id": "stu", "label": "Stocks/use"},
                {"id": "mm_extension", "label": "Managed money"},
                {"id": "mm_flow", "label": "Money flow"},
                {"id": "seasonal", "label": "Seasonal"},
                {"id": "demand", "label": "Demand"},
                {"id": "condition", "label": "Condition"},
            ],
            "rows": grains,
            "figures": [],
        },
        {
            "id": "energy",
            "title": "Energy",
            "columns": [
                {"id": "energy_level", "label": "Stocks vs 5-yr"},
                {"id": "energy_change", "label": "Week vs norm"},
                {"id": "mm_extension", "label": "Managed money"},
                {"id": "mm_flow", "label": "Money flow"},
                {"id": "seasonal", "label": "Seasonal"},
            ],
            "rows": energy_rows,
            "figures": [],
        },
        {
            "id": "cattle",
            "title": "Cattle",
            "columns": [
                {"id": "on_feed", "label": "On feed"},
                {"id": "placements", "label": "Placements"},
                {"id": "cutout", "label": "Cutout"},
                {"id": "mm_extension", "label": "Managed money"},
                {"id": "mm_flow", "label": "Money flow"},
                {"id": "seasonal", "label": "Seasonal"},
            ],
            "rows": cattle_rows,
            "figures": cattle_figs,
        },
    ]
    for section in sections:
        total = sum(item["score"]["score"] for item in section["rows"])
        scored = sum(item["score"]["scored"] for item in section["rows"])
        section["score"] = {"score": total, "scored": scored, "label": score_label(total, cfg)}
    return {
        "generated_at": datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "config": cfg,
        "rules": rule_book(cfg),
        "sections": sections,
    }


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
            print(" ", item["label"], item["score"], " ".join(bits))


if __name__ == "__main__":
    main()

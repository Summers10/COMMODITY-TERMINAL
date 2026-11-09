"""Parse the published WASDE PDF text. No country summing.

World and U.S. supply figures are read from the WASDE tables. A value the
report does not print is left absent. Callers must not fill those gaps.
"""
from __future__ import annotations

import re


def flatten(text: str) -> str:
    text = text.replace("filler", " ")
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text)


def _f(raw: str) -> float:
    return float(raw.replace(",", ""))


def _kt(raw: str) -> int:
    """Million metric tons (or million bales) as printed -> thousand units."""
    return int(round(_f(raw) * 1000))


_FIVE = r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)"
_WHEAT_TAIL = (
    rf"2024/25 {_FIVE} 2025/26 \(Est.\) {_FIVE} "
    rf"2026/27 \(Proj.\) Sep {_FIVE} 2026/27 \(Proj.\) Oct {_FIVE}"
)


def _five_rows(groups):
    """pr, ts, ex, dc, es for 2024, 2025, sep, oct."""
    keys = ("pr", "ts", "ex", "dc", "es")
    labels = ("2024", "2025", "sep", "oct")
    out = {}
    for i, label in enumerate(labels):
        chunk = groups[i * 5:(i + 1) * 5]
        out[label] = {k: _kt(v) for k, v in zip(keys, chunk)}
    return out


def _parse_wheat_block(block: str):
    m = re.search(rf"Wheat {_WHEAT_TAIL}", block)
    if not m:
        return None
    return _five_rows(m.groups())


def _corn_like(flat: str, anchor: str, n_hist_groups: int):
    """Corn/soy world rows: 7 numbers (bs, pr, im, feed_or_crush, dc, ex, es)."""
    return None


def parse_wasde(text: str) -> dict:
    flat = flatten(text)
    grains_at = flat.find("World and U.S. Supply and Use for Grains")
    if grains_at < 0:
        raise ValueError("WASDE grains supply table not found")
    us_at = flat.find("United States", grains_at + 40)
    world_block = flat[grains_at:us_at]
    # US wheat sits immediately after the United States header, before Foreign.
    foreign_at = flat.find("Total foreign is equal to world minus United States", us_at)
    us_block = flat[us_at:foreign_at if foreign_at > us_at else us_at + 4000]

    wheat_world = _parse_wheat_block(world_block)
    wheat_us = _parse_wheat_block(us_block)
    if not wheat_world or wheat_world["oct"]["pr"] < 700_000:
        raise ValueError("WASDE world wheat production was not read")
    if not wheat_us:
        raise ValueError("WASDE U.S. wheat balance was not read")

    corn = _parse_corn(flat)
    soy = _parse_soy(flat)
    oil = _parse_soyoil(flat)
    meal = _parse_soymeal(flat)
    cotton = _parse_cotton(flat)
    beef = _parse_beef(flat)
    steers = _parse_steer_price(flat)
    ident = re.search(r"WASDE - (\d+)", flat)
    dated = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4})", flat)

    return {
        "wasde_number": ident.group(1) if ident else None,
        "dated": dated.group(0) if dated else None,
        "wheat_world": wheat_world,
        "wheat_us": wheat_us,
        "corn": corn,
        "soy": soy,
        "soyoil": oil,
        "soymeal": meal,
        "cotton": cotton,
        "beef": beef,
        "steer_price": steers,
    }


def _seven(groups):
    keys = ("bs", "pr", "im", "fd", "dc", "ex", "es")
    return {k: _kt(v) for k, v in zip(keys, groups)}


def _parse_corn(flat: str):
    start = flat.find("World Corn Supply and Use")
    chunk = flat[start:start + 12000] if start >= 0 else ""
    hist = re.search(
        r"World 3/ ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ",
        chunk,
    )
    y_at = chunk.find("2025/26 Est.")
    y2526 = re.search(
        r"World 3/ ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ",
        chunk[y_at:],
    ) if y_at >= 0 else None
    cur = re.search(
        r"World Corn Supply and Use 1/ \(Cont'd\.\).*?World 3/ Sep "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) Oct "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)",
        flat,
    )
    us = re.search(
        r"World Corn Supply and Use 1/ \(Cont'd\.\).*?United States Sep "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) Oct "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)",
        flat,
    )
    if not (hist and y2526 and cur and us):
        raise ValueError("WASDE world/U.S. corn table was not read")
    return {
        "2024": _seven(hist.groups()),
        "2025": _seven(y2526.groups()),
        "sep": _seven(cur.groups()[:7]),
        "oct": _seven(cur.groups()[7:]),
        "us_sep": _seven(us.groups()[:7]),
        "us_oct": _seven(us.groups()[7:]),
    }


def _parse_soy(flat: str):
    cur = re.search(
        r"World Soybean Supply and Use.*?2026/27 Proj\..*?World 2/ Sep "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) Oct "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)",
        flat,
    )
    us = re.search(
        r"World Soybean Supply and Use.*?2026/27 Proj\..*?United States Sep "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) Oct "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)",
        flat,
    )
    y2425 = re.search(
        r"World Soybean Supply and Use.*?World 2/ ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ",
        flat,
    )
    y2526_at = flat.find("2025/26 Est. World 2/", flat.find("World Soybean Supply and Use"))
    y2526_nums = re.findall(r"[\d,]+\.\d+", flat[y2526_at:y2526_at + 280])[:7] if y2526_at >= 0 else []
    y2526 = type("M", (), {"groups": lambda self: tuple(y2526_nums)})() if len(y2526_nums) == 7 else None
    if not (cur and us and y2425 and y2526):
        raise ValueError("WASDE soybean table was not read")
    return {
        "2024": _seven(y2425.groups()),
        "2025": _seven(y2526.groups()),
        "sep": _seven(cur.groups()[:7]),
        "oct": _seven(cur.groups()[7:]),
        "us_sep": _seven(us.groups()[:7]),
        "us_oct": _seven(us.groups()[7:]),
    }


def _six(groups):
    keys = ("bs", "pr", "im", "dc", "ex", "es")
    return {k: _kt(v) for k, v in zip(keys, groups)}


def _parse_soyoil(flat: str):
    cur = re.search(
        r"World Soybean Oil Supply and Use.*?World 2/ Sep "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) Oct "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)",
        flat,
    )
    us = re.search(
        r"World Soybean Oil Supply and Use.*?2026/27 Proj\..*?United States Sep "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) Oct "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)",
        flat,
    )
    if not (cur and us):
        raise ValueError("WASDE soybean oil table was not read")
    return {
        "sep": _six(cur.groups()[:6]),
        "oct": _six(cur.groups()[6:]),
        "us_sep": _six(us.groups()[:6]),
        "us_oct": _six(us.groups()[6:]),
    }


def _parse_soymeal(flat: str):
    """Soybean meal world table, if this edition prints one. None when it does not."""
    if "World Soybean Meal Supply and Use" not in flat and "World Soybean Meal" not in flat:
        return None
    cur = re.search(
        r"World Soybean Meal Supply and Use.*?World 2/ Sep "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) Oct "
        r"([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+) ([\d,.]+)",
        flat,
    )
    if not cur:
        return None
    return {"sep": _six(cur.groups()[:6]), "oct": _six(cur.groups()[6:])}


def _parse_cotton(flat: str):
    m = re.search(
        r"Supply and Use for Cotton.*?World 2024/25 "
        rf"{_FIVE} 2025/26 \(Est.\) {_FIVE} 2026/27 \(Proj.\) Sep {_FIVE} 2026/27 \(Proj.\) Oct {_FIVE}",
        flat,
    )
    us = re.search(
        r"Supply and Use for Cotton.*?United States 2024/25 "
        rf"{_FIVE} 2025/26 \(Est.\) {_FIVE} 2026/27 \(Proj.\) Sep {_FIVE} 2026/27 \(Proj.\) Oct {_FIVE}",
        flat,
    )
    if not (m and us):
        raise ValueError("WASDE cotton table was not read")
    return {"world": _five_rows(m.groups()), "us": _five_rows(us.groups())}


def _lbs(raw: str) -> int:
    return int(round(_f(raw)))


def _parse_beef(flat: str):
    m = re.search(
        r"Beef 2025 ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d.]+) "
        r"2026 Proj\. Sep ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d.]+) "
        r"Oct ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+) ([\d.]+)",
        flat,
    )
    if not m:
        raise ValueError("WASDE beef supply table was not read")
    g = m.groups()
    keys = ("bs", "pr", "im", "ts", "ex", "es", "dc", "per_capita")

    def row(offset):
        vals = {}
        for i, k in enumerate(keys):
            raw = g[offset + i]
            vals[k] = _f(raw) if k == "per_capita" else _lbs(raw)
        return vals

    return {"2025": row(0), "sep": row(8), "oct": row(16)}


def _parse_steer_price(flat: str):
    """Annual 5-area steer price, Sep and Oct projections, dollars per cwt."""
    m = re.search(
        r"Sep Proj\. ([\d.]+) [\d.]+ [\d.]+ [\d.]+ [\d.]+ [\d.]+ Oct Proj\. ([\d.]+)",
        flat,
    )
    if not m:
        return None
    return {"sep": _f(m.group(1)), "oct": _f(m.group(2)), "unit": "$/cwt",
            "note": "WASDE annual 5-area direct steer price, total all grades"}


def attach_official_us_units(result: dict, prior: dict, text: str) -> None:
    """U.S. area and yield printed in the WASDE bushel tables."""
    flat = flatten(text)
    wheat = re.search(
        r"U\.S\. Wheat Supply and Use.*?Area Harvested ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) "
        r".*?Yield per Harvested Acre ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)",
        flat,
    )
    corn = re.search(
        r"CORN September October Million Acres Area Planted [\d.]+ [\d.]+ [\d.]+ [\d.]+ "
        r"Area Harvested ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) Bushels "
        r"Yield per Harvested Acre ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)",
        flat,
    )

    def write(comm, acres, yields):
        us = result.setdefault(comm, {}).setdefault("United States", {})
        for year, ac, yl in (("2024", acres[0], yields[0]), ("2025", acres[1], yields[1])):
            us.setdefault(year, {})["ah_ac"] = int(round(ac * 1000))
            us[year]["yl_bu"] = yl
        us.setdefault("2026", {})["ah_ac"] = int(round(acres[3] * 1000))
        us["2026"]["yl_bu"] = yields[3]
        slot = prior.setdefault(comm, {}).setdefault("United States", {}).setdefault("2026", {})
        slot["ah_ac"] = int(round(acres[2] * 1000))
        slot["yl_bu"] = yields[2]

    if wheat:
        g = [float(x) for x in wheat.groups()]
        write("Wheat", g[:4], g[4:])
    if corn:
        g = [float(x) for x in corn.groups()]
        write("Corn", g[:4], g[4:])


def apply_to_psd(result: dict, parsed: dict) -> dict:
    """Write WASDE world/U.S. rows onto the PSD country file. Returns the prior block."""
    prior = {}

    def put(comm, country, year, fields, vintage):
        clean = {k: v for k, v in fields.items() if k in ("bs", "pr", "im", "ts", "dc", "ex", "es")}
        if vintage == "sep":
            prior.setdefault(comm, {}).setdefault(country, {})[year] = clean
            return
        slot = result.setdefault(comm, {}).setdefault(country, {}).setdefault(year, {})
        slot.update(clean)

    ww = parsed["wheat_world"]
    for year in ("2024", "2025"):
        put("Wheat", "World", year, ww[year], "oct")
    put("Wheat", "World", "2026", ww["oct"], "oct")
    put("Wheat", "World", "2026", ww["sep"], "sep")
    wu = parsed["wheat_us"]
    for year in ("2024", "2025"):
        put("Wheat", "United States", year, wu[year], "oct")
    put("Wheat", "United States", "2026", wu["oct"], "oct")
    put("Wheat", "United States", "2026", wu["sep"], "sep")

    corn = parsed["corn"]
    for year in ("2024", "2025"):
        put("Corn", "World", year, corn[year], "oct")
    put("Corn", "World", "2026", corn["oct"], "oct")
    put("Corn", "World", "2026", corn["sep"], "sep")
    put("Corn", "United States", "2026", corn["us_oct"], "oct")
    put("Corn", "United States", "2026", corn["us_sep"], "sep")

    soy = parsed["soy"]
    for year in ("2024", "2025"):
        put("Soybeans", "World", year, soy[year], "oct")
    put("Soybeans", "World", "2026", soy["oct"], "oct")
    put("Soybeans", "World", "2026", soy["sep"], "sep")
    put("Soybeans", "United States", "2026", soy["us_oct"], "oct")
    put("Soybeans", "United States", "2026", soy["us_sep"], "sep")

    oil = parsed["soyoil"]
    put("Soybean Oil", "World", "2026", oil["oct"], "oct")
    put("Soybean Oil", "World", "2026", oil["sep"], "sep")
    put("Soybean Oil", "United States", "2026", oil["us_oct"], "oct")
    put("Soybean Oil", "United States", "2026", oil["us_sep"], "sep")

    if parsed.get("soymeal"):
        meal = parsed["soymeal"]
        put("Soybean Meal", "World", "2026", meal["oct"], "oct")
        put("Soybean Meal", "World", "2026", meal["sep"], "sep")

    cot = parsed["cotton"]
    for year in ("2024", "2025"):
        put("Cotton", "World", year, cot["world"][year], "oct")
        put("Cotton", "United States", year, cot["us"][year], "oct")
    put("Cotton", "World", "2026", cot["world"]["oct"], "oct")
    put("Cotton", "World", "2026", cot["world"]["sep"], "sep")
    put("Cotton", "United States", "2026", cot["us"]["oct"], "oct")
    put("Cotton", "United States", "2026", cot["us"]["sep"], "sep")

    # Drop the feed column that _seven stored via put's skip... put skips fd. Good.
    # World corn/soy have no published total supply in these tables. Do not invent ts.
    for comm in ("Corn", "Soybeans", "Soybean Oil"):
        for year, rec in result.get(comm, {}).get("World", {}).items():
            rec.pop("ts", None)
            rec.pop("fd", None)
    return prior

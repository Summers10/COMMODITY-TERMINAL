# Commodity Terminal

Research terminal for grains, oilseeds, softs, energy, and cattle. Every figure is taken from an official published source. A missing figure reads **not available**.

## Signal summary

The summary page is a rule-based board. Each cell is bullish, bearish, neutral, or a dash. The thresholds live in `config/signals.json` and are copied into `data/signals.json` when `scripts/build_signals.py` runs. The Rules block on the page is that same text.

| Rule | Threshold |
| --- | --- |
| Stocks/use percentile, every year on the sheet including the current year | the same rank the Fundamentals page prints. At or below the 33rd percentile bullish; at or above the 67th bearish. A stocks revision the other way makes the cell neutral. |
| Managed money, last 156 weeks | at or above the 85th percentile is extended long (bearish); at or below the 15th is extended short (bullish). |
| Money flow | both the 1-week and 4-week changes in managed-money net up, or both down. Mixed or zero is neutral. |
| Seasonal | average of the typed Peak Trading Research scores for this calendar week and the next four, wrapping from December into January. +1 or higher is bullish, −1 or lower is bearish. The same scores are reused every year and do not expire. No typed score is a dash. |
| Colour | each cell on its own: bullish green, bearish red, neutral plain. The cell shows the figure only. A missing figure is a dash with no colour. No row total and no section score. |
| Demand | export commitment versus a year ago, the same percent the Exports page uses. At least +5% is bullish and at least −5% is bearish. Canola uses CGC exports versus a year ago with the same band. |
| Energy stocks | 3% versus the 5-year average. Gas uses the published WNGSR percent. Petroleum uses the computed percent. Energy has no seasonal column. |
| Energy week versus normal | 3 percentage points versus the same-week percent change of the prior five years. |
| Live cattle supply and marketings | Cattle on Feed printed percent of a year ago. At or below 98 is bullish and at or above 102 is bearish. |
| Feeder placements | the same printed percent, reversed: at or above 102 is bullish and at or below 98 is bearish. |
| Feeder supply outside feedlots | the percent printed in the January and July Cattle report. At or below 98 is bullish and at or above 102 is bearish. It stays current until 10 days after the next scheduled release. |

A cell older than its cadence (WASDE and AAFC 45 days, the monthly Cattle on Feed figures 45 days, the weekly feeds 14, weather 2) is a dash. The semiannual outside-feedlots figure stays until 10 days after the next January 31 or July 31. Seasonal scores are not on that clock. The summary lists each feed's as-of date, the last successful run, and whether it is OK or stale. `scripts/build_signals.py` runs after each fetch. Update the typed Peak scores, and `SEASONALS_REVIEWED`, only when the chart itself changes.

## Pages

- Summary
- Fundamentals (grains and oilseeds, softs, energy, cattle, and the crop calendar for the selected commodity)
- CFTC
- Export sales
- Weather glance for the grain and oilseed stations (station and region, 90-day and 30-day precip, 7-day temperature, forecast days 1–7 and 8–14, 14-day high/low, SEAS5, then ENSO and US drought), with the Peak seasonal table underneath. Coffee, sugar and cocoa origins are not on this page.

Live cattle and feeder cattle positioning is only on the CFTC page.

## Secrets

Add these in the repository Actions secrets if the workflow should refresh that source. Nothing is committed.

| Secret | Used by |
| --- | --- |
| `EIA_API_KEY` | Not used. Energy is read from the public WPSR and WNGSR files. |
| `FRED_API_KEY` | Not used. |

## Data

Scheduled workflows in `.github/workflows` fetch each source and commit the JSON. A failed fetch exits non-zero and leaves the previous file in place.

# Commodity Terminal

Research terminal for grains, oilseeds, energy, crop progress and cattle. Every figure is taken from an official published source. A missing figure reads **not available**.

## Signal summary

The summary page is a rule-based board. Each cell is bullish, bearish, neutral, or a dash. The thresholds live in `config/signals.json` and are copied into `data/signals.json` when `scripts/build_signals.py` runs. The Rules block on the page is that same text.

| Rule | Threshold |
| --- | --- |
| Stocks/use percentile of the prior 10 years | at or below the 33rd percentile bullish; at or above the 67th bearish. A stocks revision the other way makes the cell neutral. |
| Managed money, last 156 weeks | at or above the 85th percentile is extended long (bearish); at or below the 15th is extended short (bullish). |
| Money flow | both the 1-week and 4-week changes in managed-money net up, or both down. Mixed or zero is neutral. |
| Seasonal | average of the typed Peak Trading Research scores for this calendar week and the next four, wrapping from December into January. +1 or higher is bullish, −1 or lower is bearish. The same scores are reused every year and do not expire. No typed score is a dash. |
| Score | bullish +1, bearish −1, neutral 0. Dashes are excluded. +2 or higher is Supportive, −2 or lower is Bearish, otherwise Neutral. |
| Demand | export commitment versus a year ago, the same percent the Exports page uses. At least +5% is bullish and at least −5% is bearish. Canola uses CGC exports versus a year ago with the same band. |
| Canola exports | CGC crop-year exports versus the same week a year ago, 3% either way. |
| Crop condition | 3 points versus the printed 5-year average, or versus year ago. Outside the months in the config the cell says out of season. |
| Energy stocks | 3% versus the 5-year average. Gas uses the published WNGSR percent. Petroleum uses the computed percent. |
| Energy week versus normal | 3 percentage points versus the same-week percent change of the prior five years. |
| Cattle on feed and placements | printed percent of a year ago, 98 and 102. |
| Boxed beef | a 1% band on the four-week change. The file has one print, so the cell is a dash. |

A cell older than its cadence (wasde and AAFC 45 days, crop progress 21, the weekly feeds 14) is a dash. Seasonal scores are not on that clock. `scripts/build_signals.py` runs after each fetch. Update the typed Peak scores, and `SEASONALS_REVIEWED`, only when the chart itself changes.

## Pages

- Summary
- USDA balances (WASDE world rows, PSD country rows, CGC canola toggle)
- CFTC
- Seasonals
- Export sales
- Weather and crop calendar
- Energy (EIA WPSR and WNGSR)
- Crop progress
- Cattle (NASS on feed and inventory, AMS slaughter and prices, WASDE beef)

Live cattle and feeder cattle positioning is only on the CFTC page.

## Secrets

Add these in the repository Actions secrets if the workflow should refresh that source. Nothing is committed.

| Secret | Used by |
| --- | --- |
| `NASS_API_KEY` | US crop progress (NASS Quick Stats). Cattle on feed does not need it. |
| `EIA_API_KEY` | Not used. Energy is read from the public WPSR and WNGSR files. |
| `FRED_API_KEY` | Not used. |

## Data

Scheduled workflows in `.github/workflows` fetch each source and commit the JSON. A failed fetch exits non-zero and leaves the previous file in place.

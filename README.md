# Commodity Terminal

Research terminal for grains, oilseeds, energy, crop progress and cattle. Every figure is taken from an official published source. A missing figure reads **not available**.

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

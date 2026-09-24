# 42 North — Retail Flooring Proposals

`42_North_Retail_Flooring_Proposals.xlsx` is the re-engineered proposals workbook:
an **Overview** tab (live cross-sheet totals, KPI tiles, hyperlinks to every proposal)
followed by 20 customer-facing proposal tabs on one design system (Garamond, brand
navy `#156082` / sky `#44B3E1`, grouped LABOR / MATERIALS / FREIGHT line items, a summary
block with TOTAL, 50 % deposit and balance, restyled project notes, floor plans retained).

Every quantity, unit price and line total is carried over from the original workbook
unchanged, and every total is a live formula.

## Rebuilding

```
python3 tooling/extract.py     # original.xlsx -> model.json (line items, notes, images, comments)
python3 tooling/build.py       # model.json    -> out/42_North_Retail_Flooring_Proposals.xlsx
python3 tooling/verify.py      # recalculated output vs. the original's cached values
```

The scripts expect `original.xlsx` (the source workbook) and its unzipped copy in `unz/`
next to them; see the top of each script. Recalculate the output with LibreOffice
(`recalc.py` from the xlsx skill) before running `verify.py`.

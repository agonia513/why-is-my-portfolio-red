# Daily runbook

How one issue is produced. The scheduled Claude session follows this file.

## Timeline (America/Toronto)

| When | What |
|---|---|
| ~16:15 | `fetch.yml` writes `data/<date>/market.json` to branch `draft/<date>` (retries at ~17:15). Holidays: nothing is written. |
| ~17:20 | Claude session writes the issue on `draft/<date>`, validates, sends a preview to the owner. |
| owner says 发布 | Claude merges `draft/<date>` into `main`; `pages.yml` validates again and deploys. |

## Writing the issue

Work on `draft/<date>`. Never edit `market.json` — every number on the page comes from it.
Read `market.json` first, then research the day (web search) and write:

- `meta.json` — `date`, `weekday` (周一…周五), `headline` (one line, the day's main thread),
  `summary` (01 一句话总览), `kpis` (4–6 ids from market.json, default SPX IXIC NVDA GOOGL MSFT AAPL),
  `timeline` (盘中轨迹: [[时段, 描述], …] — read the shape from `market.json` intraday),
  `tech_takeaways`, `structure` ([[标题, 结论], …], ≥2), `notes` (anything readers should know).
- `notes.json` — `stocks` {ticker: 短备注} optional; `movers` {ticker: {comment, src, url}} **required for the
  top 5 gainers and top 5 losers**, and welcome for others. Comments explain *why* (earnings, guidance,
  deal, news), cite the original report, and never guess. If no credible reason can be found, search
  harder; a placeholder like "待核实" fails the checker.
- `briefs.json` — list of {id, section, title, fact, assets, inference, src, url}. Sections:
  `news` (≥3, things that moved US stocks), `world` (≥2, geopolitics / energy / policy / regulation with
  the path to US stocks), `speaker` (≥2, Trump, Fed officials, Jensen Huang, CEOs — say when it's not
  from that day), `watch` (≥3, the next session and the week).
- `buzz.json` (optional) — short public social posts {who, platform, quote ≤80 chars, context, url}.
  Ordinary users are credited as "X网友"/"微博网友", never by handle. Never invent a post.

Rules: Chinese, paraphrase sources (no copying), one short quote at most per source, every claim has a
link, "影响推断" is analysis not advice. Any percentage typed in `meta.json` text must equal a value in
`market.json` at the precision written (fundamentals after 同比/营收/毛利率… are exempt).

## Checking

```
python3 scripts/validate.py <date> --links   # must print ✅ 通过
python3 scripts/build.py && python3 scripts/validate.py --all --rendered
```

Fix every ERROR and look at every WARN. Do not loosen the checker to make an issue pass.

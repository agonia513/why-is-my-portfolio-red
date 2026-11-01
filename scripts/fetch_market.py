#!/usr/bin/env python3
"""Fetch one trading day's market data into data/<date>/market.json.

Runs in GitHub Actions (needs internet): pip install yfinance pandas requests
  python3 scripts/fetch_market.py              # latest completed session
  python3 scripts/fetch_market.py --date 2026-10-30

Numbers on the site come from this file only; the writer never types prices.
Writes `date=` and `status=` (ok | closed | error) to $GITHUB_OUTPUT when set.
"""
import argparse
import datetime as dt
import json
import math
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
      "Accept": "application/json, text/plain, */*"}


def out(**kw):
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            for k, v in kw.items():
                f.write(f"{k}={v}\n")


def r(x, n=4):
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, n)


def frame_for(df, t, many):
    if isinstance(df.columns, pd.MultiIndex):
        if t not in df.columns.get_level_values(0):
            return None
        return df[t]
    return df if not many else None


def daily(symbols, day):
    """{symbol: {open, high, low, close, prev_close, chg_pct, range_pct, volume}} for `day`."""
    res = {}
    if not symbols:
        return res
    df = yf.download(symbols, start=day - dt.timedelta(days=12), end=day + dt.timedelta(days=1),
                     interval="1d", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    for s in symbols:
        d = frame_for(df, s, len(symbols) > 1)
        if d is None:
            continue
        d = d.dropna(subset=["Close"])
        d = d[[i.date() <= day for i in d.index]]
        if len(d) < 2 or d.index[-1].date() != day:
            continue
        row, prev = d.iloc[-1], float(d["Close"].iloc[-2])
        close = float(row["Close"])
        if not prev:
            continue
        res[s] = dict(open=r(row["Open"]), high=r(row["High"]), low=r(row["Low"]), close=r(close),
                      prev_close=r(prev), chg_pct=r((close / prev - 1) * 100, 3),
                      range_pct=r((float(row["High"]) - float(row["Low"])) / prev * 100, 3),
                      volume=int(row["Volume"]) if not math.isnan(float(row["Volume"] or 0)) else None)
    return res


def intraday(symbol, day, prev_close):
    df = yf.download(symbol, start=day, end=day + dt.timedelta(days=1), interval="5m",
                     auto_adjust=False, progress=False)
    if df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df = df.xs(symbol, axis=1, level=1) if symbol in df.columns.get_level_values(1) else df[symbol]
    idx = df.index.tz_convert("America/New_York") if df.index.tz is not None else df.index
    pts = []
    for t, c in zip(idx, df["Close"]):
        if t.date() != day or pd.isna(c):
            continue
        hm = t.strftime("%H:%M")
        if "09:30" <= hm <= "16:00":
            pts.append([hm, r(c, 2), r((float(c) / prev_close - 1) * 100, 3)])
    return pts


def nasdaq_close(symbol, day):
    """Closing price from Nasdaq's historical quote API — an independent second source."""
    sym = symbol.replace("-", ".")
    for ac in ("stocks", "etf"):
        url = (f"https://api.nasdaq.com/api/quote/{sym}/historical?assetclass={ac}"
               f"&fromdate={(day - dt.timedelta(days=7)).isoformat()}&todate={day.isoformat()}&limit=10")
        try:
            j = requests.get(url, headers=UA, timeout=20).json()
            rows = (((j or {}).get("data") or {}).get("tradesTable") or {}).get("rows") or []
            for row in rows:
                if dt.datetime.strptime(row["date"], "%m/%d/%Y").date() == day:
                    return float(row["close"].replace("$", "").replace(",", ""))
        except Exception:
            continue
    return None


NAME_JUNK = re.compile(r"\s*(,?\s*Inc\.?|Corporation|Corp\.?|Company|Co\.|Holdings?|Ltd\.?|plc|N\.V\.|L\.P\.)?\s*"
                       r"(Class [A-C] )?(Common Stock|Common Shares|Ordinary Shares|Capital Stock)\b.*$", re.I)


def clean_name(n):
    short = NAME_JUNK.sub("", n).strip().rstrip(",")
    return short or n


def latest_session():
    d = yf.download("^GSPC", period="10d", interval="1d", progress=False).dropna()
    return d.index[-1].date()


def universe():
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=25000&download=true"
    rows = requests.get(url, headers=UA, timeout=90).json()["data"]["rows"]
    mv = CFG["movers"]
    keep = {}
    for x in rows:
        sym = (x.get("symbol") or "").strip()
        try:
            cap = float(x.get("marketCap") or 0)
        except ValueError:
            cap = 0
        name = x.get("name") or ""
        if (x.get("country") != mv["country"] or cap < mv["min_market_cap"]
                or not re.fullmatch(r"[A-Z]{1,5}([./][A-Z])?", sym)
                or re.search(r"warrant|unit|preferred|depositary|right", name, re.I)):
            continue
        keep[sym.replace("/", "-").replace(".", "-")] = dict(symbol=sym, name=name, market_cap=cap,
                                                             sector=x.get("sector") or "", industry=x.get("industry") or "",
                                                             )
    return keep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="")
    a = ap.parse_args()
    day = dt.date.fromisoformat(a.date) if a.date else latest_session()
    out(date=day.isoformat())

    spx = daily(["^GSPC"], day)
    if "^GSPC" not in spx:
        print(f"{day}: no S&P 500 bar — market closed or data not ready")
        out(status="closed")
        return

    warnings = []

    def block(items, extra=()):
        data = daily([i.get("yf", i["id"]) for i in items], day)
        rows = []
        for i in items:
            d = data.get(i.get("yf", i["id"]))
            if not d:
                warnings.append(f"missing {i['id']}")
                continue
            rows.append({**{k: i[k] for k in ("id", "name", *extra) if k in i}, **d})
        return rows

    indices = block(CFG["indices"])
    watch = block(CFG["watchlist"], ("group",))
    macro = block(CFG["macro"], ("unit",))
    sectors = block(CFG["sectors"])
    for m in macro:
        if m.get("unit") == "%":  # yields: report change in basis points
            m["chg_bp"] = r((m["close"] - m["prev_close"]) * 100, 1)

    by_id = {i["id"]: i for i in indices}
    intr = {}
    for iid in CFG["intraday"]:
        sym = next(i["yf"] for i in CFG["indices"] if i["id"] == iid)
        pts = intraday(sym, day, by_id[iid]["prev_close"]) if iid in by_id else []
        if pts:
            intr[iid] = pts
        else:
            warnings.append(f"no intraday for {iid}")

    uni = universe()
    data = daily(list(uni), day)
    rows = []
    for ysym, d in data.items():
        u = uni[ysym]
        rows.append(dict(id=u["symbol"], name=clean_name(u["name"]), sector=u["sector"], industry=u["industry"],
                         market_cap=u["market_cap"], **d))
    n = CFG["movers"]["top_n"]
    gain = sorted(rows, key=lambda x: -x["chg_pct"])[:n]
    lose = sorted(rows, key=lambda x: x["chg_pct"])[:n]
    swing = sorted(rows, key=lambda x: -(x["range_pct"] or 0))[:n]

    # second, independent source: Nasdaq historical closes for the watchlist and top movers
    checks = []
    for x in watch + gain + lose:
        sym = next((w["yf"] for w in CFG["watchlist"] if w["id"] == x["id"]), x["id"])
        c2 = nasdaq_close(sym, day)
        if c2 is None:
            warnings.append(f"{x['id']}: Nasdaq 历史行情无数据，未能交叉核对")
            continue
        diff = abs(c2 / x["close"] - 1) * 100
        x["verified"] = diff <= 0.5
        checks.append(dict(id=x["id"], yahoo=x["close"], nasdaq=c2, diff_pct=r(diff, 3)))
    if not checks:  # print one raw answer so a blocked or changed API is diagnosable from the log
        try:
            probe = requests.get(f"https://api.nasdaq.com/api/quote/AAPL/historical?assetclass=stocks&fromdate={day - dt.timedelta(days=7)}&todate={day}&limit=10",
                                 headers=UA, timeout=20)
            print("nasdaq probe", probe.status_code, probe.text[:400])
        except Exception as ex:
            print("nasdaq probe failed", repr(ex))

    res = dict(date=day.isoformat(), generated_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               sources=dict(prices="Yahoo Finance（经 yfinance）", universe="Nasdaq 股票筛选器（api.nasdaq.com）", check="Nasdaq 历史行情（交叉核对收盘价）",
                            sectors="SPDR 行业 ETF 作为 GICS 板块代理"),
               universe=dict(count=len(rows), min_market_cap=CFG["movers"]["min_market_cap"], country=CFG["movers"]["country"]),
               indices=indices, watchlist=watch, macro=macro, sectors=sectors, intraday=intr,
               movers=dict(gainers=gain, losers=lose, swings=swing), crosscheck=checks, warnings=warnings)
    p = ROOT / "data" / day.isoformat() / "market.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {p} · universe {len(rows)} · warnings {len(warnings)}")
    for w in warnings:
        print("  WARN", w)
    out(status="ok")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # surface failure to the workflow
        print("ERROR", repr(ex), file=sys.stderr)
        out(status="error")
        raise

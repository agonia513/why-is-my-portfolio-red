#!/usr/bin/env python3
"""Check an issue before it can be published. Exit 1 on any error.

  python3 scripts/validate.py 2026-10-30          # one issue
  python3 scripts/validate.py --all               # every issue under data/
  python3 scripts/validate.py 2026-10-30 --links  # also request every source URL

Errors block publishing; warnings are printed for the reviewer.
"""
import argparse
import datetime as dt
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PLACEHOLDER = re.compile(r"TODO|TBD|待补|待定|待核实|未取得|暂无数据|N/A|^\s*[—-]\s*$|\?\?", re.I)
PCT = re.compile(r"(?<![\d.])([+\-−]?\d+(?:\.\d+)?)\s*%")
FUND = re.compile(r"同比|环比|营收|收入|毛利|利润|EPS|增长|增长率|增速|占比|指引|年内|今年|年初至今|预期|回收|日活|用户|份额|降至|升至")
MIN = {"news": 3, "world": 2, "speaker": 2, "watch": 3}


class Report:
    def __init__(self, day):
        self.day, self.errors, self.warnings = day, [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def bad_num(x):
    return x is None or not isinstance(x, (int, float)) or math.isnan(x) or math.isinf(x)


def text_ok(rep, where, v, required=True):
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            rep.err(f"{where}: 为空")
        return False
    if isinstance(v, str) and PLACEHOLDER.search(v):
        rep.err(f"{where}: 含占位/未完成字样「{v[:40]}」")
        return False
    return True


def url_ok(rep, where, u):
    if not isinstance(u, str) or not re.match(r"https://[^\s]+\.[^\s]+", u):
        rep.err(f"{where}: 来源链接无效「{u}」")


def check_market(rep, m):
    if m.get("date") != rep.day:
        rep.err(f"market.json 日期 {m.get('date')} 与期号 {rep.day} 不符")
    if dt.date.fromisoformat(rep.day).weekday() >= 5:
        rep.err("期号是周末，不是交易日")
    for key, cfg_key, lim in [("indices", "indices", 12), ("watchlist", "watchlist", 60), ("macro", "macro", 25), ("sectors", "sectors", 12)]:
        rows = {r["id"]: r for r in m.get(key, [])}
        for c in CFG[cfg_key]:
            r = rows.get(c["id"])
            if not r:
                rep.err(f"行情缺少 {key}/{c['id']}")
                continue
            for f in ("close", "prev_close", "chg_pct"):
                if bad_num(r.get(f)):
                    rep.err(f"行情 {key}/{c['id']}.{f} 为空或非数字")
            if not bad_num(r.get("close")) and r["close"] <= 0:
                rep.err(f"行情 {key}/{c['id']} 收盘价 ≤ 0")
            if not bad_num(r.get("chg_pct")) and abs(r["chg_pct"]) > (40 if c["id"] == "VIX" else lim):
                rep.warn(f"行情 {key}/{c['id']} 涨跌幅 {r['chg_pct']:.2f}% 异常大，请人工确认")
            if not bad_num(r.get("close")) and not bad_num(r.get("prev_close")) and not bad_num(r.get("chg_pct")):
                calc = (r["close"] / r["prev_close"] - 1) * 100
                if abs(calc - r["chg_pct"]) > 0.01:
                    rep.err(f"行情 {key}/{c['id']} 涨跌幅与收盘/前收不一致")
    for iid in CFG["intraday"]:
        pts = m.get("intraday", {}).get(iid, [])
        if len(pts) < 30:
            rep.err(f"{iid} 分时数据只有 {len(pts)} 个点（正常约 78 个）")
        elif pts[-1][0] < "15:55" and len(pts) < 70:
            rep.warn(f"{iid} 分时数据在 {pts[-1][0]} 结束，可能是半日市")
    mv = m.get("movers", {})
    for k in ("gainers", "losers", "swings"):
        if len(mv.get(k, [])) < 5:
            rep.err(f"波动榜 {k} 不足 5 只")
        for x in mv.get(k, []):
            if bad_num(x.get("chg_pct")) or bad_num(x.get("close")):
                rep.err(f"波动榜 {k}/{x.get('id')} 数据为空")
    if m.get("universe", {}).get("count", 0) < 500:
        rep.err(f"股票池只有 {m.get('universe', {}).get('count', 0)} 只，筛选数据可能没取全")
    cc = m.get("crosscheck", [])
    for c in cc:
        if c["diff_pct"] > 1:
            rep.err(f"{c['id']}: 两个数据源收盘价不一致（Yahoo {c['yahoo']} vs Stooq {c['stooq']}），需人工核实")
        elif c["diff_pct"] > 0.5:
            rep.warn(f"{c['id']}: 两个数据源收盘价相差 {c['diff_pct']:.2f}%")
    if len(cc) < len(CFG["watchlist"]) // 2:
        rep.warn(f"只有 {len(cc)} 只股票完成了第二数据源核对")
    for w in m.get("warnings", []):
        rep.warn(f"抓取警告：{w}")


def market_pcts(m):
    vals = []
    for k in ("indices", "watchlist", "macro", "sectors"):
        vals += [r["chg_pct"] for r in m.get(k, []) if not bad_num(r.get("chg_pct"))]
    for k in ("gainers", "losers", "swings"):
        for r in m.get("movers", {}).get(k, []):
            vals += [r["chg_pct"], r.get("range_pct") or 0]
    for pts in m.get("intraday", {}).values():
        if pts:  # only the day's extremes and the last print, never every 5-minute point
            vals += [min(p[2] for p in pts), max(p[2] for p in pts), pts[-1][2]]
    return vals


def check_numbers_in_text(rep, where, text, vals):
    """Every 'x.x%' the writer typed must match a market value at the precision written."""
    for mt in PCT.finditer(text or ""):
        if FUND.search((text or "")[max(0, mt.start() - 10):mt.start()]):
            continue  # 财报/基本面数字（同比、营收、毛利率…）不是当天行情，由来源链接负责
        raw = mt.group(1).replace("−", "-")
        x = abs(float(raw))
        dec = len(raw.split(".")[1]) if "." in raw else 0
        tol = 0.5 * 10 ** (-dec) + 1e-9
        if dec == 0 and x < 10:
            continue  # "跌超 5%" 这类粗略表述不强制
        if not any(abs(abs(v) - x) <= tol for v in vals):
            rep.err(f"{where}: 文中的 {mt.group(0)} 在当天行情数据里对不上")


def check_issue(day, links=False):
    rep = Report(day)
    d = ROOT / "data" / day
    files = {}
    for n in ("market", "meta", "notes", "briefs"):
        p = d / f"{n}.json"
        if not p.exists():
            rep.err(f"缺少 {n}.json")
            continue
        try:
            files[n] = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as ex:
            rep.err(f"{n}.json 不是合法 JSON：{ex}")
    if rep.errors:
        return rep
    m, meta, notes, briefs = files["market"], files["meta"], files["notes"], files["briefs"]
    check_market(rep, m)
    vals = market_pcts(m)

    for k in ("headline", "summary", "weekday"):
        text_ok(rep, f"meta.{k}", meta.get(k))
    ids = {r["id"] for k in ("indices", "watchlist", "macro") for r in m.get(k, [])}
    for k in meta.get("kpis", []):
        if k not in ids:
            rep.err(f"meta.kpis: {k} 不在行情数据里")
    if len(meta.get("kpis", [])) < 4:
        rep.err("meta.kpis 少于 4 个")
    texts = [("meta.summary", meta.get("summary"))]
    texts += [(f"meta.timeline[{i}]", t[1]) for i, t in enumerate(meta.get("timeline", []))]
    texts += [(f"meta.tech_takeaways[{i}]", t) for i, t in enumerate(meta.get("tech_takeaways", []))]
    texts += [(f"meta.structure[{i}]", t[1]) for i, t in enumerate(meta.get("structure", []))]
    for where, t in texts:
        text_ok(rep, where, t)
        check_numbers_in_text(rep, where, t, vals)
    if len(meta.get("structure", [])) < 2:
        rep.err("板块结构性结论少于 2 条")

    for w in CFG["watchlist"]:
        if w["id"] in notes.get("stocks", {}):
            text_ok(rep, f"notes.stocks.{w['id']}", notes["stocks"][w["id"]], required=False)
    need = CFG["movers"]["notes_required_top"]
    mv = m.get("movers", {})
    for k in ("gainers", "losers"):
        for x in mv.get(k, [])[:need]:
            n = notes.get("movers", {}).get(x["id"])
            if not n:
                rep.err(f"{'涨' if k == 'gainers' else '跌'}幅榜前 {need} 的 {x['id']} 没有点评")
                continue
            text_ok(rep, f"notes.movers.{x['id']}.comment", n.get("comment"))
            text_ok(rep, f"notes.movers.{x['id']}.src", n.get("src"))
            url_ok(rep, f"notes.movers.{x['id']}.url", n.get("url"))
            check_numbers_in_text(rep, f"notes.movers.{x['id']}", n.get("comment"), vals)

    seen = set()
    for i, b in enumerate(briefs):
        w = f"briefs[{i}]({b.get('section')}·{(b.get('title') or '')[:12]})"
        if b.get("id") in seen:
            rep.err(f"{w}: id 重复")
        seen.add(b.get("id"))
        for k in ("title", "fact", "inference", "src"):
            text_ok(rep, f"{w}.{k}", b.get(k))
        url_ok(rep, w, b.get("url"))
    for sec, n in MIN.items():
        c = sum(1 for b in briefs if b.get("section") == sec)
        if c < n:
            rep.err(f"{sec} 部分只有 {c} 条，至少要 {n} 条")

    bz = d / "buzz.json"
    if bz.exists():
        for i, b in enumerate(json.loads(bz.read_text(encoding="utf-8"))):
            for k in ("who", "platform", "quote", "context"):
                text_ok(rep, f"buzz[{i}].{k}", b.get(k))
            url_ok(rep, f"buzz[{i}]", b.get("url"))
            if len(b.get("quote", "")) > 80:
                rep.err(f"buzz[{i}]: 引文过长，只能短摘")

    if links:
        import urllib.request
        urls = {b["url"] for b in briefs if b.get("url")} | {n["url"] for n in notes.get("movers", {}).values() if n.get("url")}
        for u in sorted(urls):
            try:
                req = urllib.request.Request(u, method="GET", headers={"User-Agent": "Mozilla/5.0"})
                code = urllib.request.urlopen(req, timeout=20).status
                if code >= 400:
                    rep.warn(f"链接 {code}: {u}")
            except Exception as ex:
                rep.warn(f"链接打不开（可能是网站拦截爬虫）：{u} · {type(ex).__name__}")
    return rep


def check_rendered(day):
    """After build: the published page must not show a blank value."""
    errs = []
    for p in [ROOT / "site" / day / "index.html"]:
        if not p.exists():
            continue
        html = p.read_text(encoding="utf-8")
        for mt in re.finditer(r">\s*(—|-|N/A|NaN|None|undefined|null)\s*<", html):
            ctx = html[max(0, mt.start() - 80):mt.start()]
            errs.append(f"渲染页面出现空值「{mt.group(1)}」…{re.sub(r'<[^>]+>', ' ', ctx)[-50:]}")
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("day", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--links", action="store_true")
    ap.add_argument("--rendered", action="store_true", help="also scan site/ after build")
    a = ap.parse_args()
    # --all covers issues that have been written; a folder with only market.json is a draft in progress
    days = sorted(p.name for p in (ROOT / "data").iterdir() if (p / "meta.json").exists()) if a.all else [a.day]
    if not days or days == [None]:
        ap.error("give a date or --all")
    failed = False
    for day in days:
        rep = check_issue(day, a.links)
        if a.rendered:
            rep.errors += check_rendered(day)
        status = "✅ 通过" if not rep.errors else f"❌ {len(rep.errors)} 个错误"
        print(f"\n== {day} {status}，{len(rep.warnings)} 个提醒")
        for e in rep.errors:
            print("  ERROR", e)
        for w in rep.warnings:
            print("  WARN ", w)
        failed |= bool(rep.errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

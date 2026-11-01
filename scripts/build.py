#!/usr/bin/env python3
"""Build the static site from data/<YYYY-MM-DD>/*.json into site/.

Zero dependencies: standard library only. Run: python3 scripts/build.py
Each issue folder holds market.json (fetched by scripts/fetch_market.py, never
hand-edited) plus the written parts: meta.json, notes.json, briefs.json and
optionally buzz.json. Run scripts/validate.py before publishing.
"""
import html
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "site"
SITE_URL = os.environ.get("SITE_URL", "https://agonia513.github.io/why-is-my-portfolio-red/")
SITE_TITLE = "Why Is My Portfolio Red?"
SITE_SUB = "华尔街收盘日报 · 替你读完前一晚的美股"

e = lambda s: html.escape("" if s is None else str(s))


def pct(v):
    if v is None:
        return "—"
    return f"{'+' if v > 0 else ''}{v:.2f}%"


def num(v, d=2):
    return "—" if v is None else f"{v:,.{d}f}"


def tone(v):
    return "" if v is None or v == 0 else ("up" if v > 0 else "down")


def load(day):
    d = DATA / day
    j = lambda n, default=None: json.loads((d / f"{n}.json").read_text(encoding="utf-8")) if (d / f"{n}.json").exists() else default
    return dict(meta=j("meta"), market=j("market"), notes=j("notes", {}), briefs=j("briefs", []), buzz=j("buzz", []))


# ---------- charts (static SVG, styled by CSS classes) ----------

def svg_intraday(series, names):
    """series: {id: [[HH:MM, price, pct], ...]} drawn as % change from previous close."""
    W, H, l, r, t, b = 640, 260, 52, 96, 16, 28
    mins = lambda hm: int(hm[:2]) * 60 + int(hm[3:]) - 570
    allp = [p[2] for pts in series.values() for p in pts] + [0]
    lo, hi = min(allp), max(allp)
    pad = (hi - lo) * 0.08 or 0.2
    lo, hi = lo - pad, hi + pad
    x = lambda hm: l + (W - l - r) * mins(hm) / 390
    y = lambda v: t + (H - t - b) * (hi - v) / (hi - lo)
    step = 0.5 if hi - lo <= 4 else 1.0
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="5 分钟走势，相对前收盘涨跌幅">']
    k = math.floor(lo / step) * step
    while k <= hi:
        if k >= lo:
            out.append(f'<line class="grid{" zero" if abs(k) < 1e-9 else ""}" x1="{l}" x2="{W-r}" y1="{y(k):.1f}" y2="{y(k):.1f}"/>'
                       f'<text class="tick" x="{l-8}" y="{y(k):.1f}" dy=".35em" text-anchor="end">{k:+.1f}%</text>')
        k += step
    for hm in ["09:30", "11:00", "12:30", "14:00", "15:30"]:
        out.append(f'<text class="tick" x="{x(hm):.1f}" y="{H-8}" text-anchor="middle">{hm}</text>')
    ends = []
    for i, (sid, pts) in enumerate(series.items()):
        if not pts:
            continue
        d = " ".join(f"{'M' if j == 0 else 'L'}{x(p[0]):.1f},{y(p[2]):.1f}" for j, p in enumerate(pts))
        out.append(f'<path class="line s{i}" d="{d}"/>')
        lowp = min(pts, key=lambda p: p[2])
        out.append(f'<circle class="dot s{i}" cx="{x(lowp[0]):.1f}" cy="{y(lowp[2]):.1f}" r="3.5"><title>{e(names[sid])} 日内低点 {lowp[0]} {lowp[2]:+.2f}%</title></circle>')
        ends.append([y(pts[-1][2]), f"{names[sid]} {pts[-1][2]:+.2f}%", i])
    ends.sort()
    for j in range(1, len(ends)):
        ends[j][0] = max(ends[j][0], ends[j - 1][0] + 16)
    for yy, label, i in ends:
        out.append(f'<text class="end s{i}" x="{W-r+6}" y="{yy:.1f}" dy=".35em">{e(label)}</text>')
    out.append("</svg>")
    return "".join(out)


def svg_sectors(sectors):
    data = sorted(sectors, key=lambda s: -s["chg_pct"])
    W, rowH, l, r = 560, 26, 128, 60
    H = rowH * len(data) + 8
    mx = max(abs(s["chg_pct"]) for s in data) or 1
    x = lambda v: l + (W - l - r) * (v + mx) / (2 * mx)
    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="板块涨跌幅">',
           f'<line class="axis" x1="{x(0):.1f}" x2="{x(0):.1f}" y1="0" y2="{H}"/>']
    for i, s in enumerate(data):
        v = s["chg_pct"]
        yy = 4 + i * rowH
        x0, x1 = sorted([x(0), x(v)])
        lx, anchor = (x(v) - 6, "end") if v < 0 else (x(v) + 6, "start")
        out.append(f'<text class="cat" x="0" y="{yy+rowH/2-2:.1f}" dy=".35em">{e(s["name"])} <tspan class="tick">{e(s["id"])}</tspan></text>'
                   f'<rect class="bar {tone(v)}" x="{x0:.1f}" y="{yy+3}" width="{max(1,x1-x0):.1f}" height="{rowH-10}" rx="2"><title>{e(s["name"])}: {pct(v)}</title></rect>'
                   f'<text class="val" x="{lx:.1f}" y="{yy+rowH/2-2:.1f}" dy=".35em" text-anchor="{anchor}">{pct(v)}</text>')
    out.append("</svg>")
    return "".join(out)


def barcell(v, mx):
    w = min(50, abs(v) / mx * 50)
    left = 50 - w if v < 0 else 50
    return f'<div class="mini"><i></i><span class="{tone(v)}" style="left:{left:.1f}%;width:{w:.1f}%"></span></div>'


def buzz_html(rows):
    if not rows:
        return ""
    cards = "".join(
        f'<figure class="buzz"><blockquote>{e(r["quote"])}</blockquote>'
        f'<figcaption><b>{e(r["who"])}</b> · {a(r["platform"], r["url"])}<br><span class="muted">{e(r["context"])}</span></figcaption></figure>'
        for r in rows)
    return f'<section><h2><span class="no">🍿</span>吃瓜群众怎么说</h2><p class="muted small">摘自公开社交媒体，仅为气氛参考，不代表本站观点</p><div class="buzzes">{cards}</div></section>'


def a(src, url):
    return f'<a href="{e(url)}" target="_blank" rel="noopener">{e(src)}</a>'


def capfmt(v):
    # market cap in USD → 亿美元 (1 亿 = 1e8)
    yi = v / 1e8
    return f"{yi/1e4:.2f} 万亿" if yi >= 1e4 else f"{yi:,.0f} 亿"


# ---------- page pieces ----------

def layout(title, body, root, desc=""):
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc or SITE_SUB)}">
<meta property="og:title" content="{e(title)}"><meta property="og:description" content="{e(desc or SITE_SUB)}">
<link rel="stylesheet" href="{root}style.css">
<link rel="alternate" type="application/rss+xml" title="{e(SITE_TITLE)}" href="{root}feed.xml">
</head><body>
<header class="site"><a class="brand" href="{root}index.html">{e(SITE_TITLE)}</a>
<nav><a href="{root}archive/index.html">往期</a><a href="{root}about/index.html">关于</a><a href="{root}feed.xml">RSS</a></nav></header>
<main>{body}</main>
<footer class="site"><p>内容由 AI 撰写、人工审核，仅供信息参考，<b>不构成投资建议</b>。数据可能有误，请以原始来源为准。</p>
<p>日报内容采用 <a href="https://creativecommons.org/licenses/by-nc/4.0/deed.zh-hans">CC BY-NC 4.0</a> 许可；网站代码采用 MIT 许可。</p></footer>
</body></html>"""


def issue_body(d, root, prev_day=None, next_day=None):
    m, mk, notes = d["meta"], d["market"], d["notes"]
    Q = {r["id"]: r for k in ("indices", "watchlist", "macro") for r in mk[k]}
    names = {r["id"]: r["name"] for r in mk["indices"]}
    stock_notes = notes.get("stocks", {})
    mover_notes = notes.get("movers", {})
    watch = sorted(mk["watchlist"], key=lambda q: q["chg_pct"])
    mx = max(abs(q["chg_pct"]) for q in watch) or 1
    B = d["briefs"]
    sec = lambda s: [b for b in B if b["section"] == s]
    MV = mk["movers"]

    def tiles():
        out = []
        for t in m["kpis"]:
            q = Q[t]
            val = f'{num(q["close"])}' + ("%" if q.get("unit") == "%" else "")
            chg = f'{q["chg_bp"]:+.1f} bp' if q.get("chg_bp") is not None else pct(q["chg_pct"])
            out.append(f'<div class="tile"><p class="lbl">{e(q["name"])} <span class="tk">{e(t)}</span></p>'
                       f'<p class="big">{val}</p><p class="chg {tone(q["chg_pct"])}">{chg}</p></div>')
        return "".join(out)

    def items(rows, labels):
        out = []
        for b in rows:
            dl = "".join(f"<dt>{lab}</dt><dd>{e(b[k])}</dd>" for lab, k in zip(labels, ["fact", "assets", "inference"]) if lab and b.get(k))
            out.append(f'<article class="item"><h3>{e(b["title"])}</h3><dl>{dl}<dt>来源</dt><dd>{a(b["src"], b["url"])}</dd></dl></article>')
        return "".join(out)

    def mover_rows(rows, metric):
        out = []
        for r in rows:
            n = mover_notes.get(r["id"])
            note = (f'{e(n["comment"])} <span class="muted">· {a(n["src"], n["url"])}</span>' if n
                    else f'<span class="muted">{e(r.get("industry") or r.get("sector") or "")}</span>')
            val = pct(r["chg_pct"]) if metric == "chg" else f'{r["range_pct"]:.2f}%'
            cls = tone(r["chg_pct"]) if metric == "chg" else ""
            extra = "" if metric == "chg" else f'<td class="r {tone(r["chg_pct"])}">{pct(r["chg_pct"])}</td>'
            out.append(f'<tr><td class="tk">{e(r["id"])}</td><td>{e(r["name"])}</td><td class="r muted">{capfmt(r["market_cap"])}</td>'
                       f'<td class="r">${num(r["close"])}</td><td class="r {cls}">{val}</td>{extra}<td>{note}</td></tr>')
        return "".join(out)

    def mover_table(title, rows, metric):
        head = ("<th class='r'>涨跌幅</th>" if metric == "chg" else "<th class='r'>日内振幅</th><th class='r'>涨跌幅</th>")
        return (f'<h3>{title}</h3><div class="scroll"><table class="t"><thead><tr><th>代码</th><th>公司</th><th class="r">市值（美元）</th>'
                f'<th class="r">收盘</th>{head}<th>点评 / 行业</th></tr></thead><tbody>{mover_rows(rows, metric)}</tbody></table></div>')

    srcs = {}
    for coll in (B, d["buzz"], list(mover_notes.values())):
        for r in coll:
            if r.get("url"):
                srcs.setdefault(r["url"], r.get("src") or f'{r.get("who")}（{r.get("platform")}）')

    pager = '<nav class="pager">'
    pager += f'<a href="{root}{prev_day}/index.html">← {prev_day}</a>' if prev_day else "<span></span>"
    pager += f'<a href="{root}{next_day}/index.html">{next_day} →</a>' if next_day else "<span></span>"
    pager += "</nav>"

    U = mk["universe"]
    macro_rows = "".join(
        f'<tr><td>{e(q["name"])}</td><td class="r">{num(q["close"])}{"%" if q.get("unit") == "%" else ""}</td>'
        f'<td class="r {tone(q["chg_pct"]) if q.get("chg_bp") is None else tone(q["chg_bp"])}">'
        f'{(format(q["chg_bp"], "+.1f") + " bp") if q.get("chg_bp") is not None else pct(q["chg_pct"])}</td>'
        f'<td class="muted">{e(q.get("unit",""))}</td></tr>' for q in mk["macro"])

    return f"""
<article class="issue">
<p class="kicker">{e(m["date"])} {e(m["weekday"])} · 收盘复盘</p>
<h1>{e(m["headline"])}</h1>

<section class="hero"><h2><span class="no">01</span>一句话市场总览</h2><p>{e(m["summary"])}</p></section>

<section><h2><span class="no">02</span>核心 KPI</h2><div class="tiles">{tiles()}</div>
<table class="t compact"><thead><tr><th>指数</th><th class="r">收盘</th><th class="r">涨跌幅</th><th class="r">日内振幅</th></tr></thead><tbody>
{"".join(f'<tr><td>{e(q["name"])}</td><td class="r">{num(q["close"])}</td><td class="r {tone(q["chg_pct"])}">{pct(q["chg_pct"])}</td><td class="r muted">{q["range_pct"]:.2f}%</td></tr>' for q in mk["indices"])}
</tbody></table></section>

<section class="two"><div class="card"><h2><span class="no">03</span>指数走势（5 分钟）</h2><p class="muted small">相对前一交易日收盘的涨跌幅，美东时间</p>{svg_intraday(mk["intraday"], names)}</div>
<div class="card"><h2>盘中轨迹</h2><ul class="timeline">{"".join(f'<li><span>{e(w)}</span><span>{e(t)}</span></li>' for w, t in m["timeline"])}</ul></div></section>

<section class="card"><h2><span class="no">04</span>重点科技股表现</h2><div class="scroll"><table class="t">
<thead><tr><th>代码</th><th>公司</th><th>链条位置</th><th class="r">收盘</th><th class="r">涨跌幅</th><th></th><th>备注</th></tr></thead><tbody>
{"".join(f'<tr><td class="tk">{e(q["id"])}</td><td>{e(q["name"])}</td><td class="muted">{e(q.get("group"))}</td><td class="r">${num(q["close"])}</td><td class="r {tone(q["chg_pct"])}">{pct(q["chg_pct"])}</td><td class="bc">{barcell(q["chg_pct"], mx)}</td><td class="muted">{e(stock_notes.get(q["id"], ""))}</td></tr>' for q in watch)}
</tbody></table></div><ul class="concl">{"".join(f"<li>{e(x)}</li>" for x in m["tech_takeaways"])}</ul></section>

<section class="card"><h2><span class="no">05</span>当日大幅波动股票</h2>
<p class="muted small">股票池：{U["count"]:,} 只在美国上市的股票（含 ADR，不含 ETF），市值 ≥ {U["min_market_cap"]/1e8:,.0f} 亿美元。</p>
{mover_table("涨幅榜", MV["gainers"], "chg")}
{mover_table("跌幅榜", MV["losers"], "chg")}
{mover_table("振幅榜（日内最高与最低之差 ÷ 前收）", MV["swings"], "range")}
</section>

<section><h2><span class="no">06</span>板块与市场结构</h2><div class="two">
<div class="card"><h3>标普 500 十一大板块</h3><p class="muted small">以 SPDR 行业 ETF 涨跌幅代表</p>{svg_sectors(mk["sectors"])}</div>
<div class="card"><h3>宏观资产</h3><table class="t"><thead><tr><th>资产</th><th class="r">收盘</th><th class="r">变动</th><th>单位</th></tr></thead><tbody>
{macro_rows}
</tbody></table></div></div>
<div class="card"><h3>结构性结论</h3><ul class="concl">{"".join(f"<li><b>{e(k)}</b>：{e(v)}</li>" for k, v in m["structure"])}</ul></div></section>

<section><h2><span class="no">07</span>影响美股的关键新闻</h2><div class="items">{items(sec("news"), ["事件事实", "影响资产", "影响推断"])}</div></section>
<section><h2><span class="no">08</span>过去 24 小时国际大事</h2><div class="items">{items(sec("world"), ["发生了什么", "相关资产", "传导路径"])}</div></section>
<section><h2><span class="no">09</span>重要人物发言</h2><div class="items">{items(sec("speaker"), ["说了什么", "", "市场含义"])}</div></section>
{buzz_html(d["buzz"])}
<section><h2><span class="no">10</span>明日 / 下周关注</h2><div class="items">{items(sec("watch"), ["内容", "相关资产", "为什么关注"])}</div></section>

<section class="card"><h2><span class="no">11</span>数据来源与说明</h2>
<ul class="concl"><li>行情：{e(mk["sources"]["prices"])}；股票池：{e(mk["sources"]["universe"])}；板块：{e(mk["sources"]["sectors"])}。数据生成于 {e(mk["generated_at"])}（UTC）。</li>
<li>价格为美东 16:00 常规交易时段收盘；期货、美债与比特币为对应品种的日线收盘。</li>
{"".join(f"<li>{e(x)}</li>" for x in m.get("notes", []))}<li>每期发布前经过自动校验：数据无空值、文中所有百分比都能在行情数据中对上。</li>
<li>“影响推断”为分析判断，不构成投资建议。</li></ul>
<ol class="srcs">{"".join(f"<li>{a(s, u)}</li>" for u, s in srcs.items())}</ol></section>
{pager}
</article>"""


CSS = """
:root{--bg:#faf9f6;--panel:#fff;--fg:#1d1d1b;--muted:#6b6a65;--line:#e6e3dc;--up:#1f8a5b;--down:#c8372d;--accent:#c8372d;--s1:#2f5d9e;
--serif:"Iowan Old Style","Songti SC","Noto Serif SC",Georgia,serif;--sans:-apple-system,"PingFang SC","Noto Sans SC","Segoe UI",sans-serif}
@media (prefers-color-scheme:dark){:root{--bg:#161614;--panel:#1f1f1c;--fg:#ecebe6;--muted:#9a988f;--line:#33322d;--up:#4cc38a;--down:#ff6b5e;--s1:#7aa7e8}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.7 var(--sans)}
a{color:inherit;text-underline-offset:3px}
header.site,footer.site,main{max-width:1080px;margin:0 auto;padding:0 16px}
header.site{display:flex;justify-content:space-between;align-items:center;padding-top:20px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.brand{font-family:var(--serif);font-size:20px;text-decoration:none;font-weight:600}.brand::before{content:"▼ ";color:var(--down)}
nav a{margin-left:16px;color:var(--muted);text-decoration:none;font-size:14px}nav a:hover{color:var(--fg)}
footer.site{border-top:1px solid var(--line);margin-top:48px;padding-top:16px;padding-bottom:40px;color:var(--muted);font-size:13px}
.kicker{color:var(--muted);font-size:13px;letter-spacing:.04em;margin:32px 0 4px}
h1{font-family:var(--serif);font-weight:500;font-size:clamp(28px,4.5vw,42px);line-height:1.2;margin:0 0 24px}
h2{font-size:17px;font-weight:600;margin:0 0 12px}h3{font-size:15px;font-weight:600;margin:0 0 8px}
.no{color:var(--muted);font-weight:400;margin-right:8px;font-variant-numeric:tabular-nums}
section{margin:0 0 28px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px;min-width:0}
.two{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr));margin-bottom:16px}
.hero{border-left:3px solid var(--accent);padding-left:20px}.hero p{font-size:17px;margin:0}
.tiles{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,9.5rem),1fr));margin-bottom:16px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.tile .lbl{margin:0;color:var(--muted);font-size:13px}.tile .big{font-family:var(--serif);font-size:26px;margin:4px 0 0;font-variant-numeric:tabular-nums}
.tile .chg{margin:2px 0 0;font-variant-numeric:tabular-nums;font-weight:600}
.up{color:var(--up)}.down{color:var(--down)}.muted{color:var(--muted)}.tk{font-variant-numeric:tabular-nums;letter-spacing:.02em}
.scroll{overflow-x:auto}
table.t{width:100%;border-collapse:collapse;font-size:13.5px}
.t th{text-align:left;font-weight:600;color:var(--muted);padding:6px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
.t td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.t .r{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
.bc{min-width:110px}.mini{position:relative;height:10px;margin-top:6px}.mini i{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--line)}
.mini span{position:absolute;top:0;height:100%;border-radius:2px}.mini span.down{background:var(--down)}.mini span.up{background:var(--up)}
.timeline{list-style:none;margin:0;padding:0;font-size:14px}.timeline li{display:grid;grid-template-columns:6.5em 1fr;gap:8px;padding:6px 0;border-bottom:1px dashed var(--line)}
.timeline li span:first-child{color:var(--muted)}
.concl{margin:12px 0 0;padding-left:1.2em;font-size:14px}
.items{display:grid;gap:12px}.item{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 20px}
.item dl{display:grid;grid-template-columns:5em 1fr;gap:4px 12px;margin:0;font-size:14px}.item dt{color:var(--muted)}.item dd{margin:0}
.srcs{columns:2 20rem;font-size:13px;color:var(--muted);padding-left:1.4em}
svg text{font:12px var(--sans);fill:var(--muted);font-variant-numeric:tabular-nums}svg text.val{fill:var(--fg)}svg text.cat{fill:var(--fg)}
svg .grid{stroke:var(--line)}svg .grid.zero{stroke:var(--muted);stroke-dasharray:3 3}
svg .line.s0{stroke:var(--fg)}svg .line.s1{stroke:var(--s1)}svg .dot.s0{fill:var(--fg)}svg .dot.s1{fill:var(--s1)}
svg text.end{font-weight:600}svg text.end.s0{fill:var(--fg)}svg text.end.s1{fill:var(--s1)}svg .axis{stroke:var(--muted)}
svg .line{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
svg .dot.down,svg .bar.down{fill:var(--down)}svg .bar.up{fill:var(--up)}
.pager{display:flex;justify-content:space-between;margin-top:24px;font-size:14px}
.arch{list-style:none;padding:0}.arch li{display:grid;grid-template-columns:7.5em 1fr;gap:12px;padding:12px 0;border-bottom:1px solid var(--line)}
.arch .d{color:var(--muted);font-variant-numeric:tabular-nums}.arch a{font-family:var(--serif);font-size:18px;text-decoration:none}
.prose{max-width:680px}
.small{font-size:13px;margin:-6px 0 12px}
.buzzes{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(min(100%,16rem),1fr))}
.buzz{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px;display:flex;flex-direction:column;justify-content:space-between;gap:10px}
.buzz blockquote{margin:0;font-family:var(--serif);font-size:18px;line-height:1.45}.buzz blockquote::before{content:"“";color:var(--down)}.buzz blockquote::after{content:"”";color:var(--down)}
.buzz figcaption{font-size:13px;line-height:1.6}
"""


def main():
    days = sorted(p.name for p in DATA.iterdir() if p.is_dir() and (p / "meta.json").exists())
    if not days:
        raise SystemExit("no issues in data/")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / "style.css").write_text(CSS, encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    issues = {day: load(day) for day in days}

    for i, day in enumerate(days):
        d = issues[day]
        prev_day = days[i - 1] if i > 0 else None
        next_day = days[i + 1] if i + 1 < len(days) else None
        title = f'{d["meta"]["headline"]} · {day} · {SITE_TITLE}'
        (OUT / day).mkdir()
        (OUT / day / "index.html").write_text(
            layout(title, issue_body(d, "../", prev_day, next_day), "../", d["meta"]["summary"]), encoding="utf-8")

    latest = days[-1]
    d = issues[latest]
    (OUT / "index.html").write_text(
        layout(f'{SITE_TITLE} · {SITE_SUB}', issue_body(d, "", days[-2] if len(days) > 1 else None, None), "", d["meta"]["summary"]),
        encoding="utf-8")

    rows = "".join(f'<li><span class="d">{day} {e(issues[day]["meta"]["weekday"])}</span><a href="../{day}/index.html">{e(issues[day]["meta"]["headline"])}</a></li>'
                   for day in reversed(days))
    (OUT / "archive").mkdir()
    (OUT / "archive" / "index.html").write_text(
        layout(f"往期 · {SITE_TITLE}", f'<p class="kicker">共 {len(days)} 期</p><h1>往期</h1><ul class="arch">{rows}</ul>', "../"), encoding="utf-8")

    about = """<div class="prose"><p class="kicker">关于</p><h1>Why Is My Portfolio Red?</h1>
<p>一个值夜班的 AI 美股研究员。每个交易日收盘后，它替你读完华尔街：发生了什么、为什么、明天看什么——不是新闻堆砌，而是把新闻和盘面对上。</p>
<h2>每期包含</h2><ol><li>一句话市场总览</li><li>核心 KPI</li><li>指数走势</li><li>重点科技股表现</li><li>当日大幅波动股票</li><li>板块与市场结构</li><li>影响美股的关键新闻</li><li>过去 24 小时国际大事</li><li>重要人物发言</li><li>明日关注</li><li>数据来源与说明</li></ol>
<h2>怎么做的</h2><p>由 AI 检索公开报道与公司公告撰写，每期发布前经人工审核。每个数字和事件都附原始来源链接；取不到可靠数据时留空，不估算。</p>
<h2>免责声明</h2><p>本站内容仅供信息参考，不构成任何投资建议。数据可能存在延迟或错误，请以原始来源为准。投资有风险，决策需自负。</p></div>"""
    (OUT / "about").mkdir()
    (OUT / "about" / "index.html").write_text(layout(f"关于 · {SITE_TITLE}", about, "../"), encoding="utf-8")

    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = "".join(
        f'<item><title>{e(issues[day]["meta"]["headline"])}（{day}）</title><link>{SITE_URL}{day}/</link><guid>{SITE_URL}{day}/</guid>'
        f'<pubDate>{datetime.strptime(day, "%Y-%m-%d").strftime("%a, %d %b %Y 21:00:00 -0400")}</pubDate><description>{e(issues[day]["meta"]["summary"])}</description></item>'
        for day in reversed(days[-30:]))
    (OUT / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(SITE_TITLE)}</title><link>{SITE_URL}</link>'
        f'<description>{e(SITE_SUB)}</description><language>zh-cn</language><lastBuildDate>{now}</lastBuildDate>{items}</channel></rss>',
        encoding="utf-8")
    print(f"built {len(days)} issue(s) → {OUT}")


if __name__ == "__main__":
    main()

# Why Is My Portfolio Red? 🔻

每个交易日收盘后，替你读完华尔街：发生了什么、为什么、明天看什么。AI 撰写，人工审核。

**网站**：https://agonia513.github.io/why-is-my-portfolio-red/

## 每期结构

1. 一句话市场总览 · 2. 核心 KPI · 3. 指数走势 · 4. 重点科技股 · 5. 当日大幅波动股
6. 板块与市场结构 · 7. 关键新闻 · 8. 国际大事 · 9. 重要人物发言 · 10. 明日关注 · 11. 数据来源

## 怎么运作

- 每期是 `data/YYYY-MM-DD/` 下的一组 JSON：`meta`、`quotes`、`levels`、`movers`、`sectors`、`briefs`。
- `scripts/build.py`（零依赖）把所有期数生成静态网站到 `site/`：首页为最新一期，另有往期、关于页和 RSS。
- 推送到 `main` 后，GitHub Actions 自动构建并发布到 GitHub Pages。
- 新一期先提交到 `draft/YYYY-MM-DD` 分支，人工审核后合并到 `main` 才会上线。

本地预览：

```
python3 scripts/build.py && python3 -m http.server -d site 8000
```

## 许可

代码：MIT（见 `LICENSE`）。日报内容：CC BY-NC 4.0（见 `LICENSE-CONTENT.md`）。

内容仅供信息参考，不构成投资建议。

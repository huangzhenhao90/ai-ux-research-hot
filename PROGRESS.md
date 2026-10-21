# PROGRESS

> 执行约定见上级目录 `用研AIHOT_执行计划.md` 第 2 节。每阶段结束在此追加。
> 记录格式：做了什么 / 命令 / 结果 / 遗留问题。

---

## 阶段 1：建仓与骨架 — ✅ 完成（2026-10-21）

**做了什么**

- `git init -b main`，工作目录 `uxhot/`
- Python 3.11.5 venv（`.venv/`）+ `requirements.txt`，装完并逐个验证导入
- 按计划 §阶段 1 建全目录骨架（`config/ prompts/ uxhot/{collect,pipeline,report,publish} scripts/ data/{state,items,reports,runs} web/ eval/ tests/ .github/workflows/`）
- `.gitignore` 覆盖 `.env .venv node_modules web/.next web/out` 等
- `LICENSE`（MIT，版权 huangzhenhao90）
- `NOTICE`：注明改编自 AIHOT（commit `a0d1e75`，MIT），并写明 **AIHOT 名称与 Logo 不在 MIT 许可范围内、本站不使用**
- `README.md`、`pyproject.toml`（pytest 配置：`testpaths=tests`、`pythonpath=.`）
- `tests/test_skeleton.py`：骨架自检 4 条

**命令与结果**

| 命令 | 结果 |
|---|---|
| `python3 -m venv .venv` | Python 3.11.5 |
| `.venv/bin/pip install -r requirements.txt` | 成功；`feedparser httpx selectolax yaml pydantic openai dateutil rapidfuzz openpyxl pytest` 全部导入 OK |
| `.venv/bin/python -m pytest -q` | `....` 4 passed |
| `git status --short` | 干净（已提交 `f79ad71`） |

**环境事实**

- Python 3.11.5 / Node v22.22.3 / npm 10.9.8 / git 2.50.1 / gh 2.87.3 / uv 0.11.18 / pnpm 11.8.0
- 前端参照 `human-ai-papers/web`：Next `16.2.10` + React `19.2.7` + TS `5.9.3`

**遗留问题（已记入待办，不影响阶段 1 验收）**

1. 计划 §阶段 6 说前端「参照 human-ai-papers 的栈」，但 `human-ai-papers/web/next.config.mjs` **并没有** `output: "export"`、也没有 `basePath`（那个站部署在 Vercel，是 SSR）。阶段 6 需要自己配静态导出，**不能照抄**。
2. 本机 httpx 必须 `trust_env=False` 并显式传 `proxy`：环境变量 `NO_PROXY` 含 `[::1]`，httpx 会把它当 URL 模式解析并抛 `Invalid port: ':1]'`。已写进 `scripts/probe_feeds.py::build_client()`，阶段 5 采集模块沿用同一写法。

---

## 阶段 2：确认决策 — ✅ 完成（2026-10-21）

**做了什么**

1. 起草 §1 决策表 D1–D12，逐条发给用户确认；**12 项全部由用户选定**，结果写入 `DECISIONS.md`。
2. 为让 **D5（信源名单）有事实依据**，提前做了信源可用性探测（计划里这一步原本属于阶段 3）。

**方法**：`scripts/probe_feeds.py` 逐个试抓；另一个「域名 × 21 条常见 feed 路径」的并发发现脚本。

**⚠️ 发现一：计划 §4.4 的信源初稿大部分不可用**

计划里直接写死的约 30 个地址，只有 9 个返回 200。其余 404/403/SSL 失败，包括：
Maze、UserTesting、User Interviews、Optimal Workshop、Great Question、Sprig、ESOMAR、MRS、Greenbook、Quirk's、Research Live、MRWeb、Insights Association、dscout People Nerds、ACM TOCHI/CHI eTOC、Journal of Usability Studies、Contentsquare、Qualtrics XM Institute。

**⚠️ 发现二：9 个「僵尸源」——能解析，但多年不更新**

只测「是否返回 200」会把死站放进首页。这 9 个已排除：

| 域名 | 最后更新 |
|---|---|
| getfeedback.com | 2017-05 |
| marvelapp.com | 2022-06 |
| boxesandarrows.com | 2022-07 |
| researchops.community | 2023-11 |
| usabilitygeek.com | 2024-01 |
| thearf.org | 2024-01 |
| pollfish.com | 2024-02 |
| uxmatters.com | 2024-03 |
| playbookux.com | 2025-07 |

→ **结论：`check_sources.py`（阶段 3）必须把「最新条目日期」也作为验收项，不能只测可达性。**

**结果**

- 实测确认 **35 个可用 feed**（HTTP 200 + 有条目 + 日期可解析）。
- 按用户决定去掉偏题 4 个（Smashing Magazine、McKinsey、JMIR、AMA）后，**最终 37 个信源**：
  - T1 官方一手 **26**（20 个 RSS + 6 个 web_list）
  - T2 学术与媒体 **9**（arXiv cs.HC、Frontiers CS、MeasuringU、Product Talk、UX Collective、Rosenfeld、Jakob Nielsen、Johnny Holland、UX Magazine）
  - hot_signal **2**（Reddit r/UXResearch、HNRSS）
- 超出计划门槛「≥30 个成功、T1 ≥10」。
- 日期解析全部正常：每个 feed 的条目都带 `published_parsed` 或 `updated_parsed`。
- 瞬时失败：`nngroup.com/feed/rss/`、`hnrss.org` 第一轮通过、第二轮超时/502，属网络抖动 → `check_sources.py` 要带重试。

**命令与结果**

| 命令 | 结果 |
|---|---|
| `.venv/bin/python scripts/probe_feeds.py` | 9/30 通过（计划初稿地址） |
| 并发发现脚本（77 域名 × 21 路径） | 25 个域名有可用 feed |
| 第二轮探测（feed-scout 子代理，约 90 域名） | 新增 15 个可用 feed |
| 活跃度分级脚本 | 35 活跃/偏冷、9 僵尸 |
| `pytest -q` | 4 passed（阶段 1 自检仍绿） |

**D12 可行性已验证（用户选择「一期就做」）**

- `ur-ai-papers` 是公开仓库：`https://github.com/huangzhenhao90/ur-ai-papers`
- 公开数据可经 raw URL 读取（已实测 200，2.2 MB）：
  `https://raw.githubusercontent.com/huangzhenhao90/ur-ai-papers/main/web/public/data/papers.json`
- 数据规模 **1857 篇**；字段含 `id / title / title_zh / journal / date / url / doi / ai_score / domain_score / tldr / topic_tags / ai_type_tags`，`ai_score` 与 `domain_score` 为 1–5 分。
- ⚠️ **新发现的风险**：`date` 范围到 **2027-01**（期刊提前标注未来期号）。阶段 5 的「旧文不刷屏 / freshHours」逻辑必须先处理未来日期，否则这些条目会被当成「刚发布」全部涌上首页。
- 约束：`ur-ai-papers` 是**只读上游**，不得修改、提交、推送或停用。

**D11 对阶段 8 的约束（用户选择「从零标注」）**

`scripts/sample_gold.py` 只做分层抽样与导出，**不得导出「模型均分」「模型建议」列**，避免锚定标注。

**遗留问题**

1. `testingtime`（停更 103 天）、`uxmag`（停更 112 天）偏冷，阶段 3 复验后决定去留。
2. 6 个 `web_list` 信源的选择器（`itemSelector/titleSelector/linkSelector/dateSelector`）尚未实测，阶段 3 逐个确定。
3. Maze、Outset、Conveo 为 JS 渲染，静态抓取拿不到列表，列二期候选；`lookback.com/blog` 返回 404，博客地址待查。
4. **仓库名与计划默认值不同**：用户选定 `huangzhenhao90/ai-ux-research-hot`，`siteUrl` 须为 `https://huangzhenhao90.github.io/ai-ux-research-hot`（不是计划里预填的 `/uxhot`）。

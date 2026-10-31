# URHOT · AI 用研热点

每天从研究工具官网、用研社区、HCI 学术与行业媒体收集 AI × 用户研究的动态，
用大模型预筛 + **同一标准独立打两次分**，按信源分级门槛筛出值得看的，
写成中文标题、摘要和「为什么值得看」，按天排进「精选」。

**站点**：`URHOT` · AI 用研热点（2026-10-28 由 UXHOT 改名，见 D1 修订），**真知浩见出品**
**仓库**：`huangzhenhao90/ai-ux-research-hot`（源码，计划转私有；Pages 从只放构建产物的公开站点仓库出，见 [docs/私有化与公开站点.md](docs/私有化与公开站点.md)）

> 精选流程改编自开源项目 [AIHOT](https://github.com/KKKKhazix/AIHOT)（MIT），
> 逐文件来源见 [prompts/README.md](prompts/README.md)，版权声明见 [NOTICE](NOTICE)。
> AIHOT 的名称与 Logo 不在 MIT 许可范围内，本站不使用。

---

## 它是怎么工作的

```
信源（45 个）
   ↓ 采集：RSS / 网页列表 / 外部 JSON，条件请求（ETag）
   ↓ 旧文不刷屏：首次导入只取前 N 条并归档；之后只收新条目
   ↓ 机械去重（模型步骤之前）：URL 规范化 + 标题相似度，也和已处理的条目比；重复的不再花调用
   ↓ 预筛（模型 1 次）：PASS / BLOCK / UNKNOWN
   ↓ 评分（模型 2 次，独立调用）：0–100，两次之和 ≥ 2×门槛 才够分
   ↓ 结构化（模型 1 次）：分类 / 标签 / 主体 / scope / fact
   ↓ 写作（模型 1 次）：中文标题 + 答案先行摘要 + 推荐理由
   ↓ 同事件去重：与最近 7 天精选比对，同事件且无新信息 → 不上列表，挂在原条目详情页的「其他报道」里
   ↓ 发布：静态 JSON + RSS + llms.txt
   ↓ 前端：Next.js 静态导出 → GitHub Pages
```

**成本很低**：每条资料约 3.8 次调用、约 3,600 token；日均约 ¥0.6–1.2。
详见 [交付说明.md](交付说明.md#二日均调用与费用)。

---

## 快速开始

```bash
# 1. 环境
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置密钥（可选；不配就只跑抓取，不调模型）
cp .env.example .env && $EDITOR .env      # 填 LLM_API_KEY

# 3. 跑一遍（默认零模型调用）
python scripts/run_pipeline.py --dry-run

# 4. 真跑（会花钱，需要 MODEL_CALLS_ENABLED=true）
MODEL_CALLS_ENABLED=true python scripts/run_pipeline.py --execute --limit 30

# 5. 前端
cd web && npm ci && npm run build && npx serve out
```

**三重安全阀**：只有「脚本显式 `--execute`」+「环境有 `LLM_API_KEY`」+
「`MODEL_CALLS_ENABLED=true`」同时成立才会真的调模型。默认永远零成本。

---

## 常用命令

| 命令 | 作用 |
|---|---|
| `python scripts/run_pipeline.py --dry-run` | 抓取 + 机械步骤，模型步骤只统计调用次数 |
| `python scripts/run_pipeline.py --execute --limit 30` | 真实运行 |
| `python scripts/run_pipeline.py --source nngroup` | 只跑指定信源（可重复） |
| `node web/scripts/sync-campus.mjs [index.html]` | 同步「用研校招」岗位库（默认从 GitHub 拉 uxr-campus-2027） |
| `python scripts/sync_social.py [--force]` | 同步「用研社招」岗位（抓 11 家公司招聘官网，滑动窗口见 D17；默认一天只真抓一次；并入 `data/social/manual.yaml` 里手动收录的 Boss 直聘 / 社群岗位，来源标注见 D20） |
| `python scripts/check_public_output.py [web/out]` | 公开产物自检：产物里有没有源码、配置、密钥、手动收录的私有备注（D22） |
| `python scripts/publish_site.py [--dry-run]` | 把 `web/out` 推到公开站点仓库（需要 `PUBLIC_SITE_REPO`、`SITE_DEPLOY_KEY`，见 [docs/私有化与公开站点.md](docs/私有化与公开站点.md)） |
| `python scripts/sample_gold.py` | 导出金标标注表 `eval/gold_candidates.xlsx` |
| `python scripts/sample_gold.py --convert` | 标注完转成 `eval/gold.jsonl` |
| `python scripts/eval_selection.py --split development --label v1 --execute` | 金标评测 + 门槛扫描 |
| `python scripts/backfill_scores.py --max-items 75 --execute` | 一次性：回填评分把金标样本池做大 |

---

## 怎么改

### 加 / 删信源 → `config/sources.yaml`

字段：`id` / `name` / `kind`（`rss`\|`web_list`\|`external_json`）/ `url` /
`tier`（`T1` 官方一手 / `T1_5` / `T2` 媒体与个人 / `EXCLUDE`）/ `mode` /
`entity` / `initialBackfillLimit` / `timezone`；`web_list` 还要给四个选择器。

```bash
python scripts/probe_feeds.py --url https://example.com/feed   # 先试抓
.venv/bin/python -m pytest tests/test_config.py -q             # 再验配置
```

**踩过的坑**：`web_list` 的选择器**必须先看目标页真实的链接模式再写** ——
不要假设链接都在 `/blog/` 下（dscout 用的是 `/people-nerds/`），
正则也要允许尾斜杠（Maze 的链接是 `/blog/xxx/`）。改完用
`python scripts/probe_feeds.py` 或直接抓一遍确认能抽出条目。

### 改精选标准 → `prompts/selection-score.md`

**保留结构**：输入安全边界、五轴定义（`sig`/`nov`/`cred`/`reson`/`act`）、
类型权重表、单字段输出契约（`{"attentionScore": N}`）。
只替换「什么算重要」「什么算噪声」的**例子**。

改完 `pytest -q`；提示词版本哈希会变，**已判过的资料不重算**（与 AIHOT 一致）。

### 改门槛 → `config/selection.yaml`

现在是 T1 40 / T1_5 45 / T2 50。文件里有完整的来历说明。
**计划要求按金标评测结果改，别凭感觉** —— 也见
[交付说明.md](交付说明.md#1-门槛是按分布定的不是按金标验证的最重要)。

### 手动收录社招岗位 → `data/social/manual.yaml`

Boss 直聘截图、社群里看到的岗位，整理进这个文件（格式与例子见文件开头的注释）。页面上每个岗位都标来源：官网 / Boss直聘 / 社群，
**官网和 Boss 直聘都有的只标官网**（D20）。里面的 `internal` 私有备注永远不会发布。⚠️ 这个文件只放在私有仓库里。

### 埋点 → `docs/埋点方案.md`

各功能的 PV / UV：百度统计已写进每个页面（站点 ID 在 `web/lib/baidu.ts`）。自定义事件要改走 Umami 才设 Variables `ANALYTICS_PROVIDER=umami` 与 `ANALYTICS_ID`（D21）。

### 人工干预 → `config/overrides.yaml`

支持 `select`（强制入选）/ `reject`（强制剔除）/ `category`（改分类）/ `pin`（置顶）。
匹配键用规范化 URL 或 `urlPrefix`。**不改动 `data/items` 里的原始判断**。

### 改站名 / 文案 → `config/site.yaml`

`siteUrl` 决定前端的 `basePath`（前端从发布出的 `site.json` 读，会自动跟随）。

---

## 目录

```
config/     站点、分类、主题、信源、门槛、人工覆盖
prompts/    17 份提示词（改编自 AIHOT，逐文件注明来源）
uxhot/      Python 包
  collect/   dates(时区/未来日期) · fetch · rss · web_list · external_json
  pipeline/  normalize · prefilter · score · structure · write · dedupe · select · runner
  publish/   build_site_data · rss_out · llms_txt · validate · leak_check · site_repo
  social/    用研社招：sources(各家官网接口) · window(滑动窗口) · origin(来源标注规则) · manual(手动收录) · public(发布字段白名单) · sync
  models.py  gold.py  evalrun.py  llm.py  prompts.py  budget.py  config.py
scripts/    命令行入口
data/       items(条目) · state(游标) · runs(审计) · social(社招岗位窗口状态 + manual.yaml 手动收录)
docs/       私有化与公开站点 · 埋点方案
web/        Next.js 静态站（output: "export"）；lib/favorites*(收藏) · lib/track(埋点) · components/Brand(标志与署名)
eval/       金标评测（gold.jsonl 与标注表不进 Git）
tests/      全部离线的测试
```

---

## 测试

```bash
.venv/bin/python -m pytest -q
cd web && npm run typecheck && npm run build      # 前端
```

测试**全部离线**：用本地 fixtures + 假 LLM，不访问网络、不调模型。

---

## 许可

代码 MIT（见 [LICENSE](LICENSE)）。
信源内容版权归各发布方所有，站点默认只展示摘要与原文链接。

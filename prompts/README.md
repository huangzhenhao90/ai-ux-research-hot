# 提示词

本目录的提示词改编自开源项目 [AIHOT](https://github.com/KKKKhazix/AIHOT)（MIT，
commit `a0d1e75`）的 `industry/prompts/`，按「AI × 用户研究」行业改写。
版权与许可见仓库根目录 [NOTICE](../NOTICE)；**AIHOT 的名称与 Logo 不在 MIT 许可范围内，本站不使用**。

## 语法

由 `uxhot/prompts.py` 渲染：

- `{{siteName}}`：站名，渲染成 `UXHOT`
- `{{> 文件名}}`：包含 `prompts/<文件名>.md`，递归展开；`{{> group-method}}` 与 `{{> group-method.md}}` 等价

渲染时做三项检查，任一失败直接报错：**包含循环**、**文件缺失**、**未知占位符**。
版本哈希 = 渲染后内容的 sha256 前 8 位（`prompt_version()`），改了提示词只影响之后的新资料。

## 允许的占位符

| 类别 | 占位符 |
|---|---|
| 站点 | `siteName` |
| 运行时（每条资料） | `publishedDate` `today` `sourceName` `title` `body` `identity` `post` |
| 词表（来自 `config/taxonomy.yaml`） | `categoryGuide` `categoryCount` `categoryTags` `topicTags` `entityTags` `entities` |
| 周报 / 月报 | `kindName` `span` `sentences` `chars` `sections` `sectionsExample` |

新增占位符必须同时改 `uxhot/prompts.py` 的 `KNOWN_PLACEHOLDERS`，否则测试会拦。

## 逐文件来源

### 由执行模型（Lead）改写

| 文件 | 改编自 | 主要改动 |
|---|---|---|
| `prefilter.md` | `industry/prompts/prefilter.md` | 相关性口径由「AI 相关」改为「用户研究 / 市场研究 / 消费者洞察 / 研究方法 / 研究工具 / HCI 实证」；按 D3 写清 BLOCK 边界（纯 VR/AR 硬件、纯可视化渲染算法、纯视觉设计、增长营销、与研究方法无关的通用大模型发布）；保留 PASS/BLOCK/UNKNOWN 三档与宽召回原则 |
| `selection-score.md` | `industry/prompts/selection-score.md` | 读者由「AI 重度用户」改为「用户研究员 / UX 研究员 / 市场与消费者洞察从业者 / ResearchOps / 自己做研究的产品经理与设计师」；7 个内容类型换成用研版；**五轴权重表按用户确认值**（`research_paper` 由 `5/3/1/0/1` 改为 `3/3/2/1/1`）；「必须正常评价」与「必须压住的噪声」全部改写为用研语境（效度证据、合成用户厂商自报一致率、厂商 how-to、案例无数据等）；保留输入安全边界、事件口径校正与单字段输出契约 |
| `content-understanding.md` | `industry/prompts/content-understanding.md` | `itemType` 七类换成用研版并与分类标签建立自洽对照表；`tags` 白名单改为本站词表；推荐理由改为写「对研究员意味着什么」，禁用词表补「赋能」「黑科技」；保留六字段输出 |
| `understand.md` | `industry/prompts/understand.md` | 结构照搬：组合 `content-understanding` + 四份 `rules-*`，末尾重申只返回六字段 |
| `structure.md` | `industry/prompts/structure.md` | 简化：只输出 `category / tags / subjects / scope / fact`；分类边界改用研（工具发布判定、仅价格或配额变化记「功能更新」）；保留 fact 的当前动作 vs 背景发布辨析与 conditions 摘录规则 |
| `group-pair.md` | `industry/prompts/group-pair.md` | 简化为三选一 `same / followup / different` 加 `hasNewInfo`；写明 `same` 且 `hasNewInfo=false` 不进精选只进全部动态 |
| `group-definitions.md` | `industry/prompts/group-definitions.md` | 定义按用研语境改写（同一份报告、同一次调研、同一场访谈的不同报道算同一次发生） |
| `group-method.md` | `industry/prompts/group-method.md` | 判断方法与「日期不能证明先后」的要求照搬，例子改用研 |

### 由子代理改写（`prompts/_provenance-support.json` 有逐条记录）

| 文件 | 改编自 | 主要改动 |
|---|---|---|
| `safety.md` | `industry/prompts/safety.md` | 原样移植（该文件与行业无关） |
| `rules-anti-hallucination.md` | `industry/prompts/rules-anti-hallucination.md` | 保留全部 9 条；第 4 条补入样本量、百分比、显著性、量表名 |
| `rules-self-contained-title.md` | `industry/prompts/rules-self-contained-title.md` | 保留 6 条；例子全部换成用研场景（工具版本号 teaser、AI 主持访谈、洞察库） |
| `rules-answer-first-summary.md` | `industry/prompts/rules-answer-first-summary.md` | 保留 5 条；字数区间维持 30–70 字；影响对象改为「研究者或行业」 |
| `rules-domain.md` | `industry/prompts/rules-domain.md` | 通用 AI 术语 16 条照搬；**新增 12 条用研术语固定译法**（可用性测试、合成用户/合成受访者、AI 主持访谈、主题分析、亲和图、卡片分类、树测试、甄别问卷、洞察库、样本库、编码者一致性、日记研究）；新增用研缩写（UXR/UX/CX/ResearchOps/NPS/CSAT/CES/VoC/JTBD/SUS/A/B）与量表组；中国厂商一节改为调研公司优先中文品牌名 |
| `summarize-article.md` | `industry/prompts/summarize-article.md` | 摘要 80–160 字、最多 3 句；「优先保留」改用研语境（工具名 + 版本、样本量、效应量或一致性指标、benchmark、价格、可用性） |
| `summarize-article-empty.md` | `industry/prompts/summarize-article-empty.md` | 原样移植 |
| `summarize-short-post.md` | `industry/prompts/summarize-short-post.md` | 保留翻译任务与 10–15 字标题；**新增**一条用研语境的「优先保留」（AIHOT 原文件没有这条，它在 `summarize-long-post.md` 里） |
| `translate-body.md` | `industry/prompts/translate-body.md` | 基本照搬；角色改为「用户研究 / 科技新闻译者」 |
| `report-period.md` | `industry/prompts/report-period.md` | 基本照搬；「公司、产品、工具和人名照条目写」 |

### 未移植

`group-batch.md`、`group-signal.md`、`story-digest.md`、`identity-context.md`、`mend-wording.md`、
`summarize-long-post*.md`、`report-period-sections.md`、`report-period-no-sections.md`、
`translate-post.md` —— 对应功能一期不做（事件聚簇、综述、热榜、X 帖子）。

## 测试

`tests/test_prompts.py` 守住这些契约：

- 18 份提示词全部能 strict 渲染，无残留占位符、无未知引用；
- 渲染器会拦循环引用、缺失文件、未知占位符、未赋值占位符（负例证明）；
- 提示词里不出现 AIHOT 名字、不夹带 HTML 注释；
- 计划 §4 的 grep：`OpenAI` / `Anthropic` / `model_release` / `模型发布` 只允许出现在
  `prefilter.md` 与 `selection-score.md` 的「泛 AI 模型发布属边界外/噪声」规则里；
- **评分权重表必须与用户确认值一致**（解析 markdown 表格逐格比对，每行和为 10）；
- `rules-domain.md` 必须包含计划 §4.4 要求的 12 条用研术语译法；
- 版本哈希稳定，且内容或 `siteName` 变化时哈希必变。

## 改动提示词的注意事项

1. **不要改结构**：输入安全边界、五轴定义、类型权重、单字段输出契约、JSON 格式都是下游代码依赖的。
2. **不要凭感觉改门槛**：门槛在 `config/selection.yaml`，只在阶段 8 按用户标注的金标评测结果改。
3. 改完跑 `pytest -q`；提示词版本哈希会变，已判过的资料不会重算（与 AIHOT 一致）。

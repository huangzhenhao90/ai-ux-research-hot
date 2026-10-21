# 日报 / 周报 JSON 契约

> 由 Lead 定，`uxhot/report/`（生成）与 `uxhot/publish/`（透传）都必须遵守。
> 改动此文件需同步两处实现。

## 落盘路径

| 期别 | 路径 |
|---|---|
| 日报 | `data/reports/daily/YYYY-MM-DD.json` |
| 周报 | `data/reports/weekly/YYYY-Www.json` |

日期用**北京时间**的日界；周用 ISO 周（`YYYY-Www`，如 `2026-W43`）。

发布时由 `publish/` **原样透传**到 `web/public/data/reports/{daily,weekly}/`，
只做「能解析 + 不含 `body` + 文件名合法」三项检查，不解析报告内部结构。

## 通用要求

- 全部时间字段是 ISO 8601 **带时区**字符串。
- **不得包含 `body`（原文全文）**。
- 顶层必须有 `kind`（`daily` / `weekly`）、`siteName`、`generatedAt`。

## 日报（`kind: "daily"`）

```json
{
  "kind": "daily",
  "date": "2026-10-22",
  "siteName": "UXHOT",
  "generatedAt": "2026-10-22T00:05:00+00:00",
  "window": { "start": "2026-10-21T00:00:00+00:00", "end": "2026-10-22T00:00:00+00:00" },
  "empty": false,
  "stats": { "selectedCount": 12, "newTools": 3, "briefCount": 8 },
  "headline": { "...": "见下方 ItemRef" },
  "highlights": [ { "...": "ItemRef" } ],
  "sections": [
    { "key": "tools", "label": "工具", "items": [ { "...": "ItemRef" } ] }
  ],
  "briefs": [
    { "id": "abc123", "titleZh": "某平台发布 AI 访谈功能", "url": "https://…",
      "sourceId": "dovetail-blog", "sourceName": "Dovetail Blog" }
  ]
}
```

- `window` 覆盖**前一天 08:00 到当天 08:00（北京时间）**，输出成 UTC。
- `empty: true` 时 `headline` 为 `null`、`highlights`/`sections`/`briefs` 为空数组，
  页面显示「今日无重要更新」。
- 正文最多 12 条（`headline` + `highlights` + `sections` 里的条目合计）；
  `briefs` 最多 10 条。
- 同一 `sourceId` 在正文里最多 2 条。
- `stats.newTools` = `category == "tools"` 且 `itemType == "tool_launch"` 的条数，
  报头显示成「N 款新工具」（单位取自 `taxonomy.release.unit`）。

### ItemRef（日报里引用一条精选的最小字段集）

```json
{
  "id": "abc123",
  "titleZh": "某平台发布 AI 访谈功能",
  "summaryZh": "……",
  "reason": "……",
  "category": "tools",
  "categoryLabel": "工具",
  "sourceId": "dovetail-blog",
  "sourceName": "Dovetail Blog",
  "tier": "T1",
  "url": "https://…",
  "publishedAt": "2026-10-21T09:00:00+00:00",
  "avgScore": 88.0,
  "importance": 88.0,
  "tags": ["工具发布", "AI 访谈"],
  "relatedIds": ["def456"]
}
```

- `categoryLabel` 取自 `taxonomy.categories` 的 `label`。
- `sourceName` 取自 `config/sources.yaml` 的 `name`。
- `importance = avgScore + 5 × (同事件独立来源数 − 1)`。
- `relatedIds` 是同一事件的其他条目（来自 `relation` 为 `same` / `followup` 的组）。

## 周报（`kind: "weekly"`）

```json
{
  "kind": "weekly",
  "week": "2026-W43",
  "siteName": "UXHOT",
  "generatedAt": "2026-10-26T02:00:00+00:00",
  "window": { "start": "2026-10-19T00:00:00+00:00", "end": "2026-10-26T00:00:00+00:00" },
  "overview": "本周……",
  "overviewSource": "model",
  "stats": { "itemCount": 20, "dailyCount": 7 },
  "sections": [
    { "key": "tools", "label": "工具", "lead": "本节导读（可为空）", "items": [ { "...": "ItemRef" } ] }
  ]
}
```

- `overviewSource` 只能是 `"model"`（模型写的）或 `"template"`（名字/数字校验不过时换的模板句）。
- 周报只汇编日报，取前 20 件，同一事件跨天只算一件。
- 模型只写 `overview` 与各 `sections[].lead`，**不增删条目**。

## 索引文件

`publish/` 生成 `reports/daily/index.json` 与 `reports/weekly/index.json`：

```json
{
  "generatedAt": "2026-10-22T00:05:00+00:00",
  "kind": "daily",
  "count": 30,
  "entries": [
    { "date": "2026-10-22", "url": "https://…/daily/2026-10-22/", "count": 12, "title": null }
  ]
}
```

- 按日期**倒序**（最新在前）。
- `url` 形如 `{siteUrl}/daily/{date}/`。
- `count` / `title` 取不到就给 `null`。

---

## 实现确认（Lead 裁定，2026-10-21）

报告层实现时提出的 8 个歧义点，裁定如下（实现已按此完成）：

1. **`date` 是「出刊日」**，窗口 = `day_bounds_bj(date − 1 天)`。
   即窗口 `[D−1 08:00, D 08:00)`（北京），**起点闭、终点开**：
   正好前一天 08:00 归本期，正好当天 08:00 归下一期。
   一条资料的归属由**入选时刻 `Item.selectedAt`** 决定（不是发布时间）。
2. **`sections` 只装正文第 5–12 条**，三部分（`headline` / `highlights` / `sections`）互不重复，
   合计 ≤ 12。这是计划 §5.4「前 12 条进正文」的正确读法。
3. **`stats.selectedCount` = 窗口内 `status == SELECTED` 的条数**（计划「入选条数」字面义），
   与正文条数可以不同。
4. **`stats.newTools` 按条数**，统计窗口内全部入选条目，不限正文。
5. **`empty` = 正文为空**；此时 `headline = null` 且三个数组全空，保证
   `empty ⇔ headline == null` 这个不变式。
6. **周报 `sections[].lead` 恒为 `""`**：计划 §5.5 写「模型只写总述」，所以一期不写栏目导读。
   `prompts/report-period.md` 里的 `{{sections}}` / `{{sectionsExample}}` 传空值。
   二期若要栏目导读，需扩提示词渲染 + 加名字/数字校验。
7. **周报排序只用「位置 + 分数」**（计划 §5.5 措辞），同分按最早出现日期、再按 id 稳定排序。
8. **出刊脚本不在报告层**：`build_daily` / `build_weekly` 是纯函数，不读盘不写盘。
   「已出的不重写、错过的补出」由 `scripts/build_daily.py` 与 `scripts/build_weekly.py` 负责。

### 模型补充（Lead 已改）

`Item` 增加了 **`selectedAt`** 字段（入选时刻）。原因：日报窗口按「入选时间」分期，
用 `publishedAt` / `discoveredAt` 近似会让补跑与延迟确认的条目落错期。
`uxhot/pipeline/select.py` 在置为 `SELECTED` 时写入该字段。

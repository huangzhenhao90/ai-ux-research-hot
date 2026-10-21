# 阶段 4 · 提示词方向性验证报告

生成时间：2026-10-21T14:00:07+00:00
模型：`deepseek-chat`
调用次数：15（失败 0），token 合计 54889（输入 54728 / 输出 161）

样本取自真实信源的真实条目，正文抓自原文页。每条跑 1 次预筛 + 2 次独立评分。

| id | 期望 | 预筛 | 评分1 | 评分2 | 均分 | 门槛 | 判定 | 方向 |
|---|---|---|---:|---:|---:|---:|---|---|
| dir-01 | select | PASS | 84 | 82 | 83.0 | 76 | select | ✅ |
| dir-02 | select | PASS | 63 | 74 | 68.5 | 76 | reject | ❌ |
| dir-03 | reject | PASS | 22 | 22 | 22.0 | 60 | reject | ✅ |
| dir-04 | reject | PASS | 34 | 31 | 32.5 | 76 | reject | ✅ |
| dir-05 | either | PASS | 58 | 58 | 58.0 | 60 | reject | ✅ |

## 逐条依据

### dir-01 · Digital Twins Systematically Overestimated Business Software SUS Scores

- 来源：MeasuringU（Jeff Sauro）（T2）· [原文](https://measuringu.com/digital-twins-systematically-overestimated-business-software-sus-scores/?utm_source=rss&utm_medium=rss&utm_campaign=digital-twins-systematically-overestimated-business-software-sus-scores)
- 期望：**select** —— 有对照实验的效度证据，且结论是反直觉的否定性发现（合成用户高估 SUS 分数）。计划 §4.2「必须正常评价」明确包含此类，且写了「结论正反都算」。
- 预筛：`PASS` —— 合成用户效度实证研究
- 两次评分：[84, 82]，均分 83.0，门槛 76
- 系统判定：**select**　方向：一致 ✅

### dir-02 · Inspectable LLM-Simulated Participants for Qualitative Interview Rehearsal

- 来源：arXiv cs.HC（T2）· [原文](https://arxiv.org/abs/2610.27333)
- 期望：**select** —— 论文类，直接研究「LLM 模拟受访者用于定性访谈演练」，属于 AI × 用研核心议题，给出可检查的模拟参与者设计。计划 §4.2「必须正常评价」包含论文的新实验与新发现。
- 预筛：`PASS` —— LLM模拟受访者用于访谈预演方法研究
- 两次评分：[63, 74]，均分 68.5，门槛 76
- 系统判定：**reject**　方向：不一致 ❌

### dir-03 · Migrated SR Webinar page: Scaling research: Building an enterprise engine

- 来源：Qualtrics（T1）· [原文](https://www.qualtrics.com/events/X4-on-demand/scaling-research-workday/)
- 期望：**reject** —— 研讨会报名页（Webinar page），标题里就是「Add to calendar」。计划 §4.2「必须压住的噪声」第一条：研讨会报名 sig ≤ 2。注意它来自 T1 官方源，用来检验「不因为信源档位就抬分」。
- 预筛：`PASS` —— 企业级研究规模化引擎与反馈体系实践
- 两次评分：[22, 22]，均分 22.0，门槛 60
- 系统判定：**reject**　方向：一致 ✅

### dir-04 · Design v ADHD

- 来源：UX Collective（T2）· [原文](https://uxdesign.cc/design-vs-adhd-4411c3b81d1b?source=rss----138adf9c44c---4)
- 期望：**reject** —— 泛设计科普（ADHD 与设计），与「AI 如何改变研究工作」无实质关系，应被预筛 BLOCK 或拿到很低分。用来检验预筛边界是否够严。
- 预筛：`PASS` —— 涉及ADHD用户研究与协同设计方法实证
- 两次评分：[34, 31]，均分 32.5，门槛 76
- 系统判定：**reject**　方向：一致 ✅

### dir-05 · 9 Digital Twins you can build today (and exactly what they’ll do for you)

- 来源：Dovetail Blog（T1）· [原文](https://dovetail.com/blog/9-digital-twins-you-can-build-today/)
- 期望：**either** —— 边界样本：厂商自己的 listicle（「9 个今天就能建的 Digital Twins」）。一面是可复用的具体清单（act 高），一面是厂商引流软文（计划要求 sig ≤ 2）。方向合理即可：偏低分或中等分都能接受，不应进高分区。
- 预筛：`PASS` —— Dovetail数字孪生研究工具功能与实践
- 两次评分：[58, 58]，均分 58.0，门槛 60
- 系统判定：**reject**　方向：一致 ✅

## 结论

方向一致 **4/5**。

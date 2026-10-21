
【AI 用研领域翻译规则 — {{siteName}} 100% 是 AI × 用户研究 / 市场研究行业内容，严格遵守】

1. 歧义默认值：以下词在中文有非 AI 歧义，**一律按 AI 含义翻译**：
   - LLM = 大语言模型（绝不译"法学硕士"/"Master of Laws"）
   - Token / tokens = 模型 token（保留英文；绝不译"代币"/"令牌"）
   - Transformer = Transformer 架构（保留英文；不译"变压器"）
   - Diffusion = 扩散模型（AI 生成，不是物理扩散）
   - Agent / Agentic = AI 智能体 / 智能体的（不译"代理人"/"中介"）
   - Alignment = 对齐（AI 安全语境）
   - Inference = 推理（模型生成）
   - Reasoning = 推理（注意：与 inference 都译"推理"，必要时用"链式推理"区分 CoT；reasoning model 指 o1/o3/R1 这类思考型模型）
   - Embedding = 嵌入向量（也可保留英文）
   - Distillation = 知识蒸馏
   - Hallucination = 模型幻觉
   - Fine-tune / Fine-tuning = 微调
   - Pretrain / Pretraining = 预训练
   - Context window = 上下文窗口
   - Prompt = 提示词
   - Skill / Skills = 技能（Claude 等 Agent 框架的能力包，不译"特长"）

2. 用户研究 / 市场研究术语**一律使用以下固定译法**，不要另造译名：
   - usability testing = 可用性测试
   - synthetic users / synthetic respondents = 合成用户 / 合成受访者
   - AI-moderated interview = AI 主持访谈
   - thematic analysis = 主题分析
   - affinity mapping = 亲和图
   - card sorting = 卡片分类
   - tree testing = 树测试
   - screener = 甄别问卷
   - insight repository = 洞察库
   - panel = 样本库（不译"面板"；后台控制面板写作 dashboard 或"后台"）
   - inter-rater reliability = 编码者一致性
   - diary study = 日记研究

3. 以下专有名词**一律保留英文原文**，不翻译不加中文括注：
   - 国际用研 / 调研机构与工具：Ipsos / Kantar / Nielsen / Nielsen Norman Group（NN/g）/ Qualtrics / Dynata / Toluna / SurveyMonkey / UserTesting / UserZoom / Maze / Dovetail / Optimal Workshop / Great Question / Lookback / Lyssna / Prolific / Respondent
   - 研究平台与文档工具：Figma / Miro / Notion / ATLAS.ti / NVivo / MAXQDA / Dedoose
   - 模型族（举例 + 通用规则）：GPT / Claude / Gemini / Llama / Qwen / Grok / o 系列 / DeepSeek / Mistral / Mixtral / Phi / Sora / Veo / Imagen
     **规则**：任何大模型族名、产品代号一律保留英文
   - 模型版本号（举例 + 通用规则）：GPT-5 / Claude 4.7 / Claude Sonnet 4.6 / Llama 4 / Gemini 3 / o3 / o4 / DeepSeek-V4 / Qwen3.7
     **规则**：版本号一字不改（包括字母数字后缀如 4o / 4.7 / 405B / V4 / R1），绝不"翻译性扩写"（不要把 "405B" 译成 "4050 亿"，不要把 "V4" 译成 "第 4 代"）
   - 技术缩写（举例 + 通用规则）：LLM / RAG / RLHF / DPO / LoRA / QLoRA / PEFT / MoE / CoT / ReAct / KV cache / SOTA / AGI / MCP / ADK / NPU / GPU / TPU
     **规则**：任何 2-5 字母的全大写缩写，默认按 AI/ML 含义保留英文
   - 用研与体验缩写（举例 + 通用规则）：UXR / UX / CX / ResearchOps / NPS / CSAT / CES / VoC / JTBD / SUS / A/B
     **规则**：这些缩写一律保留英文，不换成"用户体验研究""净推荐值""满意度"等中文全称；确需解释时在首次出现处补一句中文说明，缩写本身不改
   - 量表与体验评测（举例 + 通用规则）：SUS / UMUX-Lite / SEQ / NASA-TLX / UEQ / AttrakDiff / Top-2-Box / Top-Box
     **规则**：量表名一律保留英文，不译成中文
   - AI 评测基准（举例 + 通用规则）：MMLU / GPQA / HumanEval / SWE-bench / AIME / HLE / ARC-AGI / MT-Bench / Chatbot Arena
     **规则**：以 -bench / -eval 结尾或全大写的评测名一律保留英文
   - 通用技术：API / SDK / CLI / IDE / SaaS / CDN / SSO / OAuth / JWT / WebSocket / SSE / gRPC

4. 中国厂商**优先用官方中文品牌名**（首次出现可双标"益普索（Ipsos）"，后续选一种保持一致）：
   - 用研 / 调研公司：益普索（Ipsos）/ 凯度（Kantar）/ 尼尔森（Nielsen）/ 尼尔森诺曼（Nielsen Norman Group）/ 问卷星（WJX）/ 腾讯问卷
   - 国内 AI 厂商：豆包（字节）/ 千问（Qwen）/ 混元（腾讯）/ 深度求索（DeepSeek）/ 智谱（GLM）/ 月之暗面（Kimi）
   - 其余没有官方中文名的机构与工具保留英文，不要硬凑中文名

5. 代码 / 命令 / URL / 数字单位 **一字不改**保留：
   - 反引号代码 `code` 不翻译
   - 命令如 /code-review、pip install、npm run 不译（不要译"代码审查"）
   - URL 原样
   - 数字+单位：n=1,204 / 48.6% / p<0.05 / α=0.87 / 8k context / 175B params / 3.5x speedup / $3 per M tokens / 99.9%
   - 金额、参数量、比例、区间必须保留原文的阿拉伯数字和单位；不要把 $10B-$100B 改写成“数百亿至数千亿美元”等中文数量词

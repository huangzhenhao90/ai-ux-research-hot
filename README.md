# UXHOT（暂名）· AI 用研热点

每天从研究工具官网、用研社区、HCI 学术与行业媒体收集 AI × 用户研究的动态，
模型双评分筛出值得看的，每天早上出日报。

> 执行计划见仓库上级目录的 `用研AIHOT_执行计划.md`（v2 静态站版）。
> 精选流程改编自 [AIHOT](https://github.com/KKKKhazix/AIHOT)（MIT），详见 [NOTICE](NOTICE)。

## 现在到哪一步了

见 [PROGRESS.md](PROGRESS.md)；待用户拍板的事项见 [DECISIONS.md](DECISIONS.md)。

## 本机开发

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

流水线命令（阶段 5 起可用）：

```bash
python scripts/run_pipeline.py --dry-run          # 默认：不调模型
python scripts/run_pipeline.py --execute --limit 30
```

默认零模型调用：只有显式 `--execute`、环境里有 `LLM_API_KEY` 且
`MODEL_CALLS_ENABLED=true` 时才会真的请求模型。

## 目录

```
config/     站点、分类、主题、信源、门槛、人工覆盖
prompts/    提示词（改编自 AIHOT，逐文件注明来源）
uxhot/      Python 包：collect / pipeline / report / publish
scripts/    命令行入口
data/       游标、条目、日报、运行审计
web/        Next.js 静态站（output: "export"）
eval/       金标评测
tests/      pytest
```

## 许可

代码 MIT（见 [LICENSE](LICENSE)）。信源内容版权归各发布方，默认只展示摘要与原文链接。

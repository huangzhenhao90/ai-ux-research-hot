"""公开产物自检：构建出来的站点（`web/out`）里不能有不该公开的东西（DECISIONS D22）。

源码仓库转私有之后，只有 `web/out` 会被推到公开仓库。推送之前这里再扫一遍：

- 路径：没有源码、配置、提示词、数据状态、密钥与环境文件；
- 内容：没有密钥特征；没有 `data/social/manual.yaml` 里 `internal` 私有备注的原文。

宁可误报也不要漏报：报错只会让这一次不发布、保留上一版，查清楚再发就行。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

# 站点根目录下不该出现的目录：这些都是源码仓库里的东西
FORBIDDEN_TOP_DIRS = frozenset({
    "prompts", "config", "uxhot", "scripts", "tests", "eval", "docs", "screenshots",
    "node_modules", ".github", ".git", "data-private",
})
# 任何位置都不该出现的文件后缀
FORBIDDEN_SUFFIXES = frozenset({
    ".py", ".pyc", ".yaml", ".yml", ".jsonl", ".pem", ".key", ".p12", ".pfx", ".sqlite", ".db",
})
# 任何位置都不该出现的文件名（小写比较）
FORBIDDEN_NAMES = frozenset({
    "jobs.json", "sources_state.json", "manual.yaml", "requirements.txt", "pyproject.toml",
    "id_rsa", "id_ed25519", "id_ecdsa",
})
# 只扫这些文本类文件的内容
TEXT_SUFFIXES = frozenset({".html", ".js", ".mjs", ".json", ".txt", ".xml", ".css", ".map", ".svg", ".md"})
MAX_SCAN_BYTES = 20 * 1024 * 1024

# 注意 URL 里的 slug：「task-analysis-for-ux-research-teams」里藏着 `sk-analysis-for-ux-…`，
# 所以 `sk-` 前面不能是字母数字，后面也不能含连字符（真 key 是连续的字母数字）；这类误报会让整次发布被拦下
SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"LLM_API_KEY"), "模型密钥的变量名"),
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{24,}"), "像是模型 API key（sk-…）"),
    (re.compile(r"(?<![A-Za-z0-9])sk-(?:proj|ant|or)-[A-Za-z0-9_-]{20,}"), "像是模型 API key（sk-proj-…）"),
    (re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{30,}"), "像是 GitHub token"),
    (re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"), "像是 GitHub 细粒度 token"),
    (re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"), "私钥"),
    (re.compile(r"(?<![A-Za-z0-9])AKIA[0-9A-Z]{16}(?![A-Za-z0-9])"), "像是 AWS access key"),
)
# 私有备注太短（几个字）会在页面里碰巧出现，不拿它判断
MIN_PRIVATE_TEXT = 4


def check_public_output(out_dir: Path, private_texts: Iterable[str] = ()) -> list[str]:
    """返回问题列表；空列表表示可以公开。"""
    out = Path(out_dir)
    if not out.is_dir():
        return [f"{out} 不是目录（还没构建？）"]

    problems: list[str] = []
    private = [t for t in (p.strip() for p in private_texts) if len(t) >= MIN_PRIVATE_TEXT]

    for entry in out.iterdir():
        if entry.name.lower() in FORBIDDEN_TOP_DIRS:
            problems.append(f"{entry.name}/：源码仓库里的目录，不该出现在公开站点里")

    for path in sorted(out.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(out).as_posix()
        name = path.name.lower()
        if name in FORBIDDEN_NAMES or name.startswith(".env") or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"{rel}：不该公开的文件")
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > MAX_SCAN_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern, what in SECRET_PATTERNS:
            if pattern.search(text):
                problems.append(f"{rel}：内容里有{what}")
        for secret in private:
            if secret in text:
                problems.append(f"{rel}：内容里有 manual.yaml 的私有备注（internal）")
                break
    return problems


def private_notes(manual_path: Path) -> list[str]:
    """手动收录岗位（manual.yaml）里每条的 `internal` 私有备注；文件不存在就是没有。"""
    from uxhot.social.manual import load_manual

    return [job.internal for job in load_manual(manual_path) if job.internal]

"""提示词渲染。

语法（与 AIHOT 一致，便于对照维护）：

- `{{siteName}}`：变量占位符，渲染时替换。
- `{{> 文件名}}`：包含 `prompts/<文件名>.md`，递归展开；`{{> group-method}}` 与
  `{{> group-method.md}}` 等价。

渲染时做三件检查：包含循环、文件缺失、未知占位符。三者都直接报错，
避免把写错的提示词静默发给模型。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from uxhot.config import ConfigBundle, Taxonomy

REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = REPO_ROOT / "prompts"

# 站点变量
SITE_PLACEHOLDERS = frozenset({"siteName"})

# 每条资料运行时注入
RUNTIME_PLACEHOLDERS = frozenset(
    {"publishedDate", "today", "sourceName", "title", "body", "identity", "post"}
)

# 从 taxonomy.yaml 注入
TAXONOMY_PLACEHOLDERS = frozenset(
    {"categoryGuide", "categoryCount", "categoryTags", "topicTags", "entityTags", "entities"}
)

# 周报/月报注入
REPORT_PLACEHOLDERS = frozenset(
    {"kindName", "span", "sentences", "chars", "sections", "sectionsExample"}
)

KNOWN_PLACEHOLDERS = (
    SITE_PLACEHOLDERS
    | RUNTIME_PLACEHOLDERS
    | TAXONOMY_PLACEHOLDERS
    | REPORT_PLACEHOLDERS
)

INCLUDE_RE = re.compile(r"\{\{\s*>\s*([A-Za-z0-9_\-\.]+)\s*\}\}")
VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

# 不是提示词的辅助文件
NON_PROMPT_FILES = frozenset({"README.md"})


class PromptError(ValueError):
    """提示词渲染失败。"""


class CircularIncludeError(PromptError):
    pass


class MissingPromptError(PromptError):
    pass


class UnknownPlaceholderError(PromptError):
    pass


class UnfilledPlaceholderError(PromptError):
    pass


def _path_for(name: str, prompts_dir: Path) -> Path:
    return prompts_dir / (name if name.endswith(".md") else f"{name}.md")


def _expand_includes(name: str, stack: tuple[str, ...], prompts_dir: Path) -> str:
    """递归展开 `{{> 文件}}`，检测循环引用。"""
    if name in stack:
        chain = " → ".join((*stack, name))
        raise CircularIncludeError(f"提示词包含循环引用：{chain}")

    path = _path_for(name, prompts_dir)
    if not path.is_file():
        raise MissingPromptError(f"提示词文件不存在：{path}")

    text = path.read_text(encoding="utf-8")

    def repl(match: re.Match[str]) -> str:
        return _expand_includes(match.group(1), (*stack, name), prompts_dir)

    return INCLUDE_RE.sub(repl, text)


def _substitute(text: str, variables: dict[str, str], strict: bool) -> str:
    unknown: set[str] = set()

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in KNOWN_PLACEHOLDERS:
            unknown.add(key)
            return match.group(0)
        if key in variables:
            return str(variables[key])
        return match.group(0)

    out = VAR_RE.sub(repl, text)

    if unknown:
        raise UnknownPlaceholderError(
            f"提示词里有未知占位符：{sorted(unknown)}（允许的占位符见 uxhot/prompts.py）"
        )

    if strict:
        leftover = VAR_RE.findall(out)
        if leftover:
            raise UnfilledPlaceholderError(f"这些占位符没有被赋值：{sorted(set(leftover))}")
        leftover_includes = INCLUDE_RE.findall(out)
        if leftover_includes:
            raise UnfilledPlaceholderError(f"这些包含没有被展开：{leftover_includes}")
        # 只查 `{{`（未展开或写坏的占位符起点）。
        # 不查 `}}`：占位符的值本身是 JSON 对象时（如 `"x": {{example}}}`），
        # 替换后天然会出现 `}}`，那是合法输出。
        if "{{" in out:
            raise UnfilledPlaceholderError("渲染结果里仍有未展开的 {{")

    return out


def load_raw(name: str, prompts_dir: Path | None = None) -> str:
    """读取提示词原文（不展开包含、不替换变量）。"""
    pdir = prompts_dir or PROMPTS_DIR
    path = _path_for(name, pdir)
    if not path.is_file():
        raise MissingPromptError(f"提示词文件不存在：{path}")
    return path.read_text(encoding="utf-8")


def render(
    name: str,
    variables: dict[str, str] | None = None,
    *,
    prompts_dir: Path | None = None,
    strict: bool = False,
) -> str:
    """渲染提示词。

    strict=False：允许已知但本次未赋值的占位符留在结果里（运行时分步注入）。
    strict=True：要求全部占位符都已赋值，且结果里不能残留 `{{`。
    """
    pdir = prompts_dir or PROMPTS_DIR
    expanded = _expand_includes(name, (), pdir)
    return _substitute(expanded, variables or {}, strict)


def prompt_version(name: str, variables: dict[str, str] | None = None, *,
                   prompts_dir: Path | None = None) -> str:
    """提示词版本 = 渲染后内容的 sha256 前 8 位（计划 §5.1）。

    改了提示词只影响之后的新资料，已判过的不重算。
    """
    rendered = render(name, variables, prompts_dir=prompts_dir)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:8]


def list_prompts(prompts_dir: Path | None = None) -> list[str]:
    """列出全部提示词文件名（不含 README 等辅助文件）。"""
    pdir = prompts_dir or PROMPTS_DIR
    return sorted(
        p.name
        for p in pdir.glob("*.md")
        if p.name not in NON_PROMPT_FILES
    )


def includes_of(name: str, prompts_dir: Path | None = None) -> set[str]:
    """这份提示词直接或间接包含的全部文件名（用于测试与文档）。"""
    pdir = prompts_dir or PROMPTS_DIR
    seen: set[str] = set()

    def walk(current: str) -> None:
        path = _path_for(current, pdir)
        if not path.is_file():
            raise MissingPromptError(f"提示词文件不存在：{path}")
        for match in INCLUDE_RE.finditer(path.read_text(encoding="utf-8")):
            child = match.group(1)
            if child not in seen:
                seen.add(child)
                walk(child)

    walk(name)
    return seen


def site_variables(cfg: ConfigBundle) -> dict[str, str]:
    return {"siteName": cfg.site.name}


def taxonomy_variables(tax: Taxonomy) -> dict[str, str]:
    return {
        "categoryGuide": tax.category_guide_text(),
        "categoryCount": str(len(tax.categories)),
        "categoryTags": "、".join(tax.categoryTags),
        "topicTags": "、".join(tax.topicTags),
        "entityTags": "、".join(tax.entityTags),
        "entities": "、".join(e.id for e in tax.entities),
    }


def base_variables(cfg: ConfigBundle) -> dict[str, str]:
    """站点 + 词表变量，所有提示词共用。"""
    return {**site_variables(cfg), **taxonomy_variables(cfg.taxonomy)}

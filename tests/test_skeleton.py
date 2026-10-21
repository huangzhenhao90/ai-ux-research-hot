"""阶段 1 骨架自检：目录结构、包可导入、仓库卫生。

这些断言守的是「骨架必须存在」这个行为，而不是具体实现写法。
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_DIRS = [
    "config",
    "prompts",
    "uxhot",
    "uxhot/collect",
    "uxhot/pipeline",
    "uxhot/report",
    "uxhot/publish",
    "scripts",
    "data/state",
    "data/items",
    "data/reports/daily",
    "data/reports/weekly",
    "data/runs",
    "web",
    "eval",
    "tests",
    ".github/workflows",
]

EXPECTED_FILES = [
    "LICENSE",
    "NOTICE",
    "README.md",
    "PROGRESS.md",
    "DECISIONS.md",
    "requirements.txt",
    ".gitignore",
]

GITIGNORE_MUST_CONTAIN = [
    ".env",
    ".venv",
    "node_modules",
    "web/.next",
    "web/out",
]


def test_skeleton_directories_exist() -> None:
    missing = [d for d in EXPECTED_DIRS if not (REPO_ROOT / d).is_dir()]
    assert not missing, f"缺少目录：{missing}"


def test_skeleton_files_exist() -> None:
    missing = [f for f in EXPECTED_FILES if not (REPO_ROOT / f).is_file()]
    assert not missing, f"缺少文件：{missing}"


def test_gitignore_covers_required_paths() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    missing = [p for p in GITIGNORE_MUST_CONTAIN if p not in text]
    assert not missing, f".gitignore 缺少：{missing}"


def test_python_package_importable() -> None:
    import uxhot
    import uxhot.collect
    import uxhot.pipeline
    import uxhot.publish
    import uxhot.report

    assert uxhot is not None

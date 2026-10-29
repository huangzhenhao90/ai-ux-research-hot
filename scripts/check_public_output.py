#!/usr/bin/env python3
"""公开产物自检：构建出来的站点里有没有不该公开的东西（DECISIONS D22）。

用法：
    python scripts/check_public_output.py                 # 检查 web/out
    python scripts/check_public_output.py web/public      # 检查别的目录
    python scripts/check_public_output.py --manual data/social/manual.yaml

退出码：0 = 可以公开；1 = 有问题（逐条打印）。
CI 的每次构建、Update 推到公开仓库之前都会跑一遍。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.publish.leak_check import check_public_output, private_notes  # noqa: E402
from uxhot.social.manual import ManualError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="公开产物自检")
    parser.add_argument("out_dir", nargs="?", default=str(REPO_ROOT / "web" / "out"))
    parser.add_argument(
        "--manual",
        default=str(REPO_ROOT / "data" / "social" / "manual.yaml"),
        help="手动收录文件；里面 internal 私有备注的原文不能出现在产物里",
    )
    args = parser.parse_args()

    try:
        secrets = private_notes(Path(args.manual))
    except ManualError as exc:
        print(f"✗ {exc}")
        return 1
    problems = check_public_output(Path(args.out_dir), secrets)
    if problems:
        print(f"✗ {args.out_dir} 里有不该公开的内容（{len(problems)} 处）：")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"✓ {args.out_dir} 可以公开（检查了路径、密钥特征与 {len(secrets)} 条私有备注）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

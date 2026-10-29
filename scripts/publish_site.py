#!/usr/bin/env python3
"""把构建好的静态站（web/out）推到公开站点仓库（DECISIONS D22）。

源码仓库是私有的，GitHub Pages 从另一个公开仓库出；那个仓库里只放构建产物。
推送前先跑泄漏自检与子路径检查，任何一步不过都不推，公开仓库保持上一版。

环境变量：
  PUBLIC_SITE_REPO       公开站点仓库，owner/name（必填）
  SITE_DEPLOY_KEY        该仓库的 deploy key（SSH 私钥内容，需要写权限）
  PUBLIC_SITE_BRANCH     推到哪个分支，默认 gh-pages（Pages 里选「从分支部署」）
  PUBLIC_SITE_BASE_PATH  自定义域名时站点所在的路径（站点在域名根就写 /）；不设就按仓库名推算
  PUBLIC_SITE_REMOTE     覆盖远程地址（试验用，比如本地裸仓库的路径）

用法：
    python scripts/publish_site.py --dry-run      # 只检查与整理，不推送
    python scripts/publish_site.py                # 推送
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from uxhot.publish.leak_check import check_public_output, private_notes  # noqa: E402
from uxhot.publish.site_repo import check_base_path, push_site, stage_site  # noqa: E402
from uxhot.social.manual import ManualError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="推送静态站到公开站点仓库")
    parser.add_argument("--out", default=str(REPO_ROOT / "web" / "out"))
    parser.add_argument("--dry-run", action="store_true", help="只检查与整理，不推送")
    args = parser.parse_args()

    out = Path(args.out)
    repo = os.environ.get("PUBLIC_SITE_REPO", "").strip()
    branch = os.environ.get("PUBLIC_SITE_BRANCH", "").strip() or "gh-pages"
    remote = os.environ.get("PUBLIC_SITE_REMOTE", "").strip() or (f"git@github.com:{repo}.git" if repo else "")
    deploy_key = os.environ.get("SITE_DEPLOY_KEY", "").strip() or None

    if not repo:
        print("✗ 没设 PUBLIC_SITE_REPO（公开站点仓库，owner/name）")
        return 1
    if repo.lower() == os.environ.get("GITHUB_REPOSITORY", "").lower():
        print("✗ PUBLIC_SITE_REPO 不能是源码仓库自己：那样源码仓库就得保持公开")
        return 1
    if not (out / "index.html").is_file():
        print(f"✗ {out}/index.html 不存在：先构建（cd web && npm run build）")
        return 1
    if not args.dry_run and not remote.startswith(("/", "file:")) and not deploy_key:
        print("✗ 没设 SITE_DEPLOY_KEY（对公开站点仓库有写权限的 deploy key）")
        return 1

    # 1. 泄漏自检
    try:
        secrets = private_notes(REPO_ROOT / "data" / "social" / "manual.yaml")
    except ManualError as exc:
        print(f"✗ {exc}")
        return 1
    problems = check_public_output(out, secrets)
    if problems:
        print("✗ 产物里有不该公开的内容，不推送：")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    # 2. 子路径要和 Pages 实际的地址一致
    mismatch = check_base_path(out, repo, os.environ.get("PUBLIC_SITE_BASE_PATH", "").strip() or None)
    if mismatch:
        print(f"✗ {mismatch}")
        return 1

    # 3. 整理并推送
    with tempfile.TemporaryDirectory(prefix="urhot-site-") as tmp:
        stage = Path(tmp) / "site"
        count = stage_site(
            out,
            stage,
            readme=REPO_ROOT / "docs" / "public-site-README.md",
            # 只放第三方致谢，不放项目自己的 LICENSE / NOTICE：完整代码是私有的，不对构建产物声明开源许可
            extras={"NOTICE": REPO_ROOT / "docs" / "public-site-NOTICE.txt"},
        )
        if args.dry_run:
            print(f"✓ 检查通过，将推送 {count} 个文件到 {repo}（分支 {branch}）；--dry-run 不推送")
            return 0
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        push_site(stage, remote, branch, message=f"站点产物 {stamp}", deploy_key=deploy_key)
    print(f"✓ 已推送 {count} 个文件到 {repo}（分支 {branch}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

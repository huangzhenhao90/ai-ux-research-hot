"""把构建好的静态站推到「公开站点仓库」（DECISIONS D22）。

源码、提示词、采集逻辑、数据状态都在私有仓库里；GitHub Pages 从另一个公开仓库出，
那个仓库里只有构建产物（HTML / JS / CSS / 公开 JSON）——也就是浏览器本来就会下载到的那些东西。

做法：每次把产物放进一个全新的、只有一个提交的 git 仓库，强推到公开仓库的分支。
公开仓库里不留历史，也就没有「某次构建里漏出去的东西」可以翻出来。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

DEPLOY_NAME = "URhot Deploy"
DEPLOY_EMAIL = "deploy@users.noreply.github.com"


def expected_base_path(repo: str, override: str | None = None) -> str:
    """GitHub Pages 把公开仓库 `owner/name` 放在 `/name/` 下（`owner.github.io` 仓库放在根）。

    `override`：自定义域名时站点在域名根（`/`）或别的子路径，由 `PUBLIC_SITE_BASE_PATH` 指定。
    """
    if override:
        return "" if override.strip("/") == "" else "/" + override.strip("/")
    owner, _, name = repo.partition("/")
    if not owner or not name:
        raise ValueError(f"PUBLIC_SITE_REPO 要写成 owner/name，现在是：{repo!r}")
    return "" if name.lower() == f"{owner.lower()}.github.io" else f"/{name}"


def check_base_path(out_dir: Path, repo: str, override: str | None = None) -> str | None:
    """产物里的 basePath 要和 Pages 实际会放的路径一致，否则页面能打开但样式与脚本全 404。

    basePath 来自 config/site.yaml 的 siteUrl（构建时写进产物）。返回错误说明，一致就返回 None。
    """
    site_json = Path(out_dir) / "data" / "site.json"
    try:
        built = json.loads(site_json.read_text(encoding="utf-8")).get("basePath", "")
    except (OSError, ValueError) as exc:
        return f"读不到 {site_json}：{exc}"
    wanted = expected_base_path(repo, override)
    if built != wanted:
        return (
            f"产物是按子路径 {built or '/'} 构建的（config/site.yaml 的 siteUrl），"
            f"但公开仓库 {repo} 的 Pages 地址会是 {wanted or '/'}。"
            "把 siteUrl 改成公开站点的真实地址再构建；用自定义域名时设置 PUBLIC_SITE_BASE_PATH。"
        )
    return None


def stage_site(out_dir: Path, stage: Path, *, readme: Path | None, extras: dict[str, Path]) -> int:
    """把产物整理成要推送的内容：站点文件 + `.nojekyll` + 说明与声明文件。返回文件数。

    `extras` 是 目标文件名 → 源文件：源码仓库里的文件（比如带项目自己许可声明的 NOTICE）不原样公开，
    公开仓库里放的是专门写给它的版本。

    `.nojekyll` 必须有：分支方式的 Pages 默认会跑 Jekyll，它会丢掉下划线开头的目录（Next 的 `_next`）。
    """
    shutil.copytree(out_dir, stage, dirs_exist_ok=True)
    (stage / ".nojekyll").write_text("", encoding="utf-8")
    if readme is not None and readme.exists():
        shutil.copyfile(readme, stage / "README.md")
    for name, source in extras.items():
        if source.exists():
            shutil.copyfile(source, stage / name)
    return sum(1 for p in stage.rglob("*") if p.is_file())


def _git(stage: Path, *args: str, env: dict[str, str] | None = None) -> None:
    result = subprocess.run(
        ["git", *args], cwd=stage, env=env, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        # 命令里可能带远程地址，输出里不会有密钥（密钥在文件里，不在命令行）
        raise RuntimeError(f"git {args[0]} 失败：{(result.stderr or result.stdout).strip()}")


def push_site(
    stage: Path,
    remote: str,
    branch: str,
    *,
    message: str,
    deploy_key: str | None = None,
) -> None:
    """在 `stage` 里建一个只有一个提交的仓库，强推到 `remote` 的 `branch`。

    `deploy_key` 是对公开仓库有写权限的 SSH 私钥（内容，不是路径）；用本地路径当 `remote` 试验时可以不给。
    """
    env = dict(os.environ)
    key_dir: Path | None = None
    try:
        if deploy_key:
            key_dir = Path(tempfile.mkdtemp(prefix="deploykey-"))
            key_file = key_dir / "id"
            # ssh 要求私钥文件以换行结尾，且只有自己能读
            key_file.write_text(deploy_key.strip() + "\n", encoding="utf-8")
            key_file.chmod(0o600)
            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {key_file} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new "
                f"-o UserKnownHostsFile={key_dir / 'known_hosts'}"
            )
        _git(stage, "init", "-q", "-b", branch)
        _git(stage, "config", "user.name", DEPLOY_NAME)
        _git(stage, "config", "user.email", DEPLOY_EMAIL)
        _git(stage, "add", "-A")
        _git(stage, "commit", "-q", "-m", message)
        _git(stage, "remote", "add", "origin", remote)
        _git(stage, "push", "-q", "--force", "origin", f"HEAD:refs/heads/{branch}", env=env)
    finally:
        if key_dir is not None:
            shutil.rmtree(key_dir, ignore_errors=True)

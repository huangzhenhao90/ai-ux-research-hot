"""私有源码 / 公开站点的拆分（DECISIONS D22）：泄漏自检、子路径检查、推送。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from uxhot.publish.leak_check import check_public_output, private_notes
from uxhot.publish.site_repo import check_base_path, expected_base_path, push_site, stage_site

REPO_ROOT = Path(__file__).resolve().parents[1]


def make_site(root: Path, base_path: str = "/urhot") -> Path:
    (root / "data").mkdir(parents=True)
    (root / "_next" / "static").mkdir(parents=True)
    (root / "index.html").write_text("<html>URhot</html>", encoding="utf-8")
    (root / "_next" / "static" / "app.js").write_text("console.log('hi')", encoding="utf-8")
    (root / "data" / "site.json").write_text(json.dumps({"basePath": base_path}), encoding="utf-8")
    return root


# ── 泄漏自检 ───────────────────────────────────────────────────────────


def test_clean_site_passes(tmp_path):
    assert check_public_output(make_site(tmp_path / "out")) == []


def test_missing_directory_is_reported(tmp_path):
    assert "不是目录" in check_public_output(tmp_path / "nope")[0]


@pytest.mark.parametrize("top", ["prompts", "config", "uxhot", "scripts", "tests", "eval", "docs", ".github", ".git"])
def test_source_directories_at_the_top_level_are_forbidden(tmp_path, top):
    out = make_site(tmp_path / "out")
    (out / top).mkdir()
    assert any(p.startswith(f"{top}/") for p in check_public_output(out))


@pytest.mark.parametrize(
    "name",
    ["run_pipeline.py", "sources.yaml", "items.jsonl", "id_rsa", "deploy.pem", ".env", ".env.production",
     "jobs.json", "sources_state.json", "manual.yaml", "pyproject.toml"],
)
def test_private_looking_files_are_forbidden_anywhere(tmp_path, name):
    out = make_site(tmp_path / "out")
    (out / "data" / name).write_text("x", encoding="utf-8")
    assert any(name in p for p in check_public_output(out))


def test_a_topic_page_named_like_a_source_directory_is_fine(tmp_path):
    """只有站点根目录下的目录名算数：/topics/config/ 这种页面路径不是源码目录。"""
    out = make_site(tmp_path / "out")
    (out / "topics" / "config").mkdir(parents=True)
    (out / "topics" / "config" / "index.html").write_text("ok", encoding="utf-8")
    assert check_public_output(out) == []


@pytest.mark.parametrize(
    ("secret", "what"),
    [
        ("LLM_API_KEY=abc", "变量名"),
        ("key = 'sk-" + "a1B2c3D4e5F6g7H8i9J0k1L2" + "'", "API key"),
        ("token ghp_" + "A" * 36, "GitHub token"),
        ("-----BEGIN " + "OPENSSH PRIVATE KEY-----", "私钥"),
        ("-----BEGIN " + "PRIVATE KEY-----", "私钥"),
    ],
)
def test_secret_shaped_content_is_flagged(tmp_path, secret, what):
    out = make_site(tmp_path / "out")
    (out / "_next" / "static" / "app.js").write_text(f"var x = \"{secret}\";", encoding="utf-8")
    problems = check_public_output(out)
    assert problems and what in problems[0]


@pytest.mark.parametrize(
    "innocent",
    [
        # 站内条目的原文链接：slug 里常有 task- / ask- / risk- / desk- 这类，不能被当成 sk- 开头的 key
        "https://www.surveymonkey.com/curiosity/ask-the-market-holiday-shopping-pricing/",
        "https://example.com/blog/task-analysis-for-ux-research-teams-in-2026",
        "https://example.com/desk-research-vs-field-research-which-one-first",
        "https://example.com/risk-assessment-framework-for-ai-moderated-interviews",
        "https://example.com/sk-" + "a-very-long-hyphenated-slug-with-many-words-in-it",
    ],
)
def test_url_slugs_are_not_mistaken_for_api_keys(tmp_path, innocent):
    out = make_site(tmp_path / "out")
    (out / "data" / "item.json").write_text(json.dumps({"url": innocent}), encoding="utf-8")
    assert check_public_output(out) == []


@pytest.mark.parametrize(
    "real",
    ["sk-" + "0123456789abcdef0123456789abcdef", "sk-proj-" + "Ab1-Cd2_Ef3" * 4, "export KEY=sk-" + "a" * 48],
)
def test_realistic_api_keys_are_still_caught(tmp_path, real):
    out = make_site(tmp_path / "out")
    (out / "data" / "item.json").write_text(json.dumps({"note": real}), encoding="utf-8")
    assert "API key" in check_public_output(out)[0]


def test_binary_files_are_not_scanned(tmp_path):
    out = make_site(tmp_path / "out")
    (out / "logo.png").write_bytes(b"\x89PNG LLM_API_KEY \x00\x01")
    assert check_public_output(out) == []


def test_internal_notes_from_manual_yaml_must_not_appear_in_the_output(tmp_path):
    manual = tmp_path / "manual.yaml"
    manual.write_text(
        "jobs:\n  - {source: community, company: 滴滴, title: 体验研究, addedAt: 2026-10-29,"
        " internal: 张三在群里分享的内推}\n",
        encoding="utf-8",
    )
    notes = private_notes(manual)
    assert notes == ["张三在群里分享的内推"]

    out = make_site(tmp_path / "out")
    assert check_public_output(out, notes) == []
    (out / "index.html").write_text("<p>张三在群里分享的内推</p>", encoding="utf-8")
    assert "internal" in check_public_output(out, notes)[0]
    # 太短的备注不拿来判断（会在页面里碰巧出现）
    assert check_public_output(out, ["群里"]) == []


def test_private_notes_without_a_manual_file_is_empty(tmp_path):
    assert private_notes(tmp_path / "missing.yaml") == []


def test_committed_public_data_passes_the_check():
    """web/public 是构建时拷进站点的那部分（公开 JSON、RSS、llms.txt），必须一直是干净的。"""
    assert check_public_output(REPO_ROOT / "web" / "public", private_notes(REPO_ROOT / "data" / "social" / "manual.yaml")) == []


# ── 子路径 ─────────────────────────────────────────────────────────────


def test_expected_base_path():
    assert expected_base_path("huangzhenhao90/urhot") == "/urhot"
    assert expected_base_path("huangzhenhao90/huangzhenhao90.github.io") == ""
    assert expected_base_path("Huang/huang.GITHUB.io") == ""
    assert expected_base_path("a/b", override="/") == ""
    assert expected_base_path("a/b", override="/docs/") == "/docs"
    with pytest.raises(ValueError):
        expected_base_path("no-slash")


def test_base_path_mismatch_is_caught_before_publishing(tmp_path):
    out = make_site(tmp_path / "out", base_path="/ai-ux-research-hot")
    message = check_base_path(out, "huangzhenhao90/urhot")
    assert message and "/ai-ux-research-hot" in message and "/urhot" in message
    assert check_base_path(out, "huangzhenhao90/ai-ux-research-hot") is None
    assert check_base_path(out, "huangzhenhao90/urhot", override="/ai-ux-research-hot") is None
    assert "读不到" in check_base_path(tmp_path / "empty", "a/b")


# ── 整理与推送 ─────────────────────────────────────────────────────────


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def test_stage_adds_nojekyll_readme_and_a_public_notice_under_its_own_name(tmp_path):
    out = make_site(tmp_path / "out")
    readme = tmp_path / "README-template.md"
    readme.write_text("# public", encoding="utf-8")
    notice = tmp_path / "public-site-NOTICE.txt"
    notice.write_text("第三方声明", encoding="utf-8")

    stage = tmp_path / "stage"
    count = stage_site(out, stage, readme=readme, extras={"NOTICE": notice, "MISSING": tmp_path / "nope"})
    assert (stage / ".nojekyll").exists() and (stage / "README.md").read_text(encoding="utf-8") == "# public"
    assert (stage / "NOTICE").read_text(encoding="utf-8") == "第三方声明" and not (stage / "MISSING").exists()
    assert not (stage / "LICENSE").exists()                      # 不对构建产物声明开源许可
    assert (stage / "_next" / "static" / "app.js").exists()      # 下划线目录要带上（所以才要 .nojekyll）
    assert count == sum(1 for p in stage.rglob("*") if p.is_file())
    assert not (out / ".nojekyll").exists()                      # 不改动构建目录


def test_the_public_notice_credits_third_parties_but_grants_no_license_to_the_site():
    """站点仓库里的 NOTICE 只致谢第三方；项目自己的 MIT 声明（见根目录 NOTICE / LICENSE）不随产物公开。"""
    notice = (REPO_ROOT / "docs" / "public-site-NOTICE.txt").read_text(encoding="utf-8")
    assert "AIHOT" in notice and "MIT" in notice            # 对上游的致谢与许可链接要在
    assert "见 LICENSE" not in notice and "以 MIT 许可证发布" not in notice


def test_push_replaces_the_branch_with_a_single_fresh_commit(tmp_path):
    bare = tmp_path / "public.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))

    for round_number, content in enumerate(("v1", "v2"), start=1):
        out = make_site(tmp_path / f"out{round_number}")
        (out / "index.html").write_text(f"<html>{content}</html>", encoding="utf-8")
        stage = tmp_path / f"stage{round_number}"
        stage_site(out, stage, readme=None, extras={})
        push_site(stage, str(bare), "gh-pages", message=f"站点产物 {content}")

    assert git(bare, "rev-list", "--count", "gh-pages") == "1"          # 强推：没有历史
    assert git(bare, "log", "-1", "--format=%s", "gh-pages") == "站点产物 v2"
    assert git(bare, "show", "gh-pages:index.html") == "<html>v2</html>"
    assert ".nojekyll" in git(bare, "ls-tree", "--name-only", "gh-pages").splitlines()
    assert git(bare, "log", "-1", "--format=%an", "gh-pages") == "URhot Deploy"


def test_push_failure_is_reported_not_swallowed(tmp_path):
    out = make_site(tmp_path / "out")
    stage = tmp_path / "stage"
    stage_site(out, stage, readme=None, extras={})
    with pytest.raises(RuntimeError, match="git push 失败"):
        push_site(stage, str(tmp_path / "does-not-exist.git"), "gh-pages", message="x")


def test_cli_refuses_to_publish_into_the_source_repo_and_checks_before_pushing(tmp_path, monkeypatch):
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("publish_site_cli", REPO_ROOT / "scripts" / "publish_site.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    out = make_site(tmp_path / "out", base_path="/urhot")
    monkeypatch.setattr(sys, "argv", ["publish_site.py", "--out", str(out), "--dry-run"])

    monkeypatch.delenv("PUBLIC_SITE_REPO", raising=False)
    assert cli.main() == 1                                            # 没设公开仓库

    monkeypatch.setenv("PUBLIC_SITE_REPO", "me/private-src")
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/private-src")
    assert cli.main() == 1                                            # 不能推回源码仓库自己

    monkeypatch.setenv("GITHUB_REPOSITORY", "me/private-src")
    monkeypatch.setenv("PUBLIC_SITE_REPO", "me/urhot")
    assert cli.main() == 0                                            # 检查通过（dry-run 不推送）

    monkeypatch.setenv("PUBLIC_SITE_REPO", "me/another-name")
    assert cli.main() == 1                                            # 子路径对不上

    monkeypatch.setenv("PUBLIC_SITE_REPO", "me/urhot")
    (out / "leak.py").write_text("x", encoding="utf-8")
    assert cli.main() == 1                                            # 产物里混进源码

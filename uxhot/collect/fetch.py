"""HTTP 抓取与正文抽取。

本机注意：Clash TUN 把域名解析成 198.18.x.x 假 IP，且环境变量 `NO_PROXY` 含 `[::1]`，
httpx 默认 `trust_env=True` 会因它抛 `Invalid port: ':1]'`。所以这里显式构造客户端、
自己读代理设置、并关掉 `trust_env`。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

import httpx
from selectolax.lexbor import LexborHTMLParser

# 完整 Chrome UA：有的站点对短 UA 返回爬虫版、对完整 UA 返回 JS 版，字节数能差数倍
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 25.0

# 正文抽取的候选容器，按优先级
BODY_SELECTORS = (
    "article",
    "main",
    "[role=main]",
    "div.post-content",
    "div.entry-content",
    "div.article-content",
    "div[class*=post-body]",
    "div[class*=rich-text]",
)

# 明显不是正文的块
STRIP_SELECTORS = (
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "iframe", "svg", "figure figcaption",
)

MIN_BODY_CHARS = 200


@dataclass
class FetchResult:
    url: str
    status: int
    text: str = ""
    etag: str | None = None
    last_modified: str | None = None
    from_cache: bool = False       # 304 命中
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == 200 and not self.error


@dataclass
class SourceState:
    """每个信源的游标与失败计数（存 data/state/sources_state.json）。"""

    etag: str | None = None
    lastModified: str | None = None
    firstImportAt: str | None = None   # 首次导入时间，用于「旧文不刷屏」
    lastFetchAt: str | None = None
    consecutiveFailures: int = 0
    lastError: str | None = None
    extra: dict = field(default_factory=dict)


def build_client(timeout: float = DEFAULT_TIMEOUT, **kwargs) -> httpx.Client:
    proxy = (
        os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
    )
    options: dict = {
        "timeout": timeout,
        "follow_redirects": True,
        "trust_env": False,
        "headers": {
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
        },
    }
    options.update(kwargs)
    if proxy:
        options["proxy"] = proxy
    return httpx.Client(**options)


def fetch(
    url: str,
    client: httpx.Client,
    *,
    state: SourceState | None = None,
) -> FetchResult:
    """带条件请求的抓取。

    有 ETag / Last-Modified 时带上；返回 304 表示没变化，调用方跳过解析。
    失败时**不推进游标**（由调用方决定），并把错误记进 state。
    """
    headers: dict[str, str] = {}
    if state is not None:
        if state.etag:
            headers["If-None-Match"] = state.etag
        if state.lastModified:
            headers["If-Modified-Since"] = state.lastModified

    try:
        resp = client.get(url, headers=headers)
    except Exception as exc:  # noqa: BLE001 - 抓取失败要如实记录，不中断整次运行
        if state is not None:
            state.consecutiveFailures += 1
            state.lastError = f"{type(exc).__name__}: {exc}"
        return FetchResult(url=url, status=0, error=f"{type(exc).__name__}: {exc}")

    if resp.status_code == 304:
        return FetchResult(url=url, status=304, from_cache=True)

    if resp.status_code != 200:
        if state is not None:
            state.consecutiveFailures += 1
            state.lastError = f"HTTP {resp.status_code}"
        return FetchResult(url=url, status=resp.status_code, error=f"HTTP {resp.status_code}")

    if state is not None:
        state.consecutiveFailures = 0
        state.lastError = None
        state.etag = resp.headers.get("etag") or state.etag
        state.lastModified = resp.headers.get("last-modified") or state.lastModified

    return FetchResult(
        url=url,
        status=200,
        text=resp.text,
        etag=resp.headers.get("etag"),
        last_modified=resp.headers.get("last-modified"),
    )


def strip_html(html: str) -> str:
    """把 HTML 变成纯文本。"""
    if not html:
        return ""
    tree = LexborHTMLParser(html)
    for selector in STRIP_SELECTORS:
        for node in tree.css(selector):
            node.decompose()
    text = tree.text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_body(html: str, *, min_chars: int = MIN_BODY_CHARS) -> str:
    """从文章页抽正文。

    优先找语义容器；都不够长就退回整页文本（总比空着好，交给下游截断）。
    """
    if not html:
        return ""
    tree = LexborHTMLParser(html)
    for selector in STRIP_SELECTORS:
        for node in tree.css(selector):
            node.decompose()

    best = ""
    for selector in BODY_SELECTORS:
        node = tree.css_first(selector)
        if node is None:
            continue
        text = re.sub(r"\s+", " ", node.text(separator=" ", strip=True)).strip()
        if len(text) > len(best):
            best = text
        if len(best) >= min_chars:
            return best

    if best:
        return best

    fallback = tree.body.text(separator=" ", strip=True) if tree.body else ""
    return re.sub(r"\s+", " ", fallback).strip()


def detect_lang(html: str, fallback: str | None = None) -> str | None:
    """从 `<html lang=...>` 猜语言。"""
    if not html:
        return fallback
    m = re.search(r"<html[^>]+lang=[\"']([A-Za-z-]+)[\"']", html, re.IGNORECASE)
    if m:
        return m.group(1).lower()[:5]
    return fallback

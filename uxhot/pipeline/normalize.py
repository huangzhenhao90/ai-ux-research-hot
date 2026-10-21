"""URL 规范化与机械去重（计划 §5.2 第 3 条）。

只做机械判断，不调模型：去追踪参数、去尾斜杠、同 URL 合并、标题相似度。
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

# 追踪参数（保留其余 query，有些站点的文章 id 就在 query 里）
TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "hsa_", "_hs", "vero_")
TRACKING_EXACT = {
    "ref", "referrer", "fbclid", "gclid", "dclid", "msclkid", "yclid",
    "igshid", "mc_cid", "mc_eid", "spm", "from", "source", "share",
    "wt_mc", "at_medium", "at_campaign", "cmpid", "campaign",
    "__twitter_impression", "guccounter", "guce_referrer", "guce_referrer_sig",
}

# 需要保留 query 的站点特征：这些站点的文章 id 在 query 里，不能整段丢掉
KEEP_QUERY_HOSTS = {
    "dl.acm.org", "journals.sagepub.com", "www.tandfonline.com",
    "rss.sciencedirect.com", "pubsonline.informs.org",
}

DEFAULT_PORTS = {"http": "80", "https": "443"}


def _is_tracking(key: str) -> bool:
    lowered = key.lower()
    if lowered in TRACKING_EXACT:
        return True
    return any(lowered.startswith(p) for p in TRACKING_PREFIXES)


def canonicalize_url(url: str) -> str:
    """规范化 URL。

    规则：
    - 小写 scheme/host，去掉默认端口
    - 去掉 fragment
    - 去掉追踪参数；其余 query 按键排序（保证参数顺序不同也视为同一 URL）
    - 去掉尾部斜杠（根路径除外）
    - 去掉 `www.` 前缀（`www.example.com` 与 `example.com` 视为同一站）
    """
    if not url:
        return ""

    parts = urlsplit(url.strip())

    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and str(parts.port) != DEFAULT_PORTS.get(scheme):
        host = f"{host}:{parts.port}"

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    # 有些站点的文章 id 在 query 里（如 ACM/SAGE 的 jc=xxx），必须保留
    keep_all = host in KEEP_QUERY_HOSTS or any(
        host.endswith(h) for h in KEEP_QUERY_HOSTS
    )
    if keep_all:
        query = parts.query
    else:
        pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not _is_tracking(k)]
        query = urlencode(sorted(pairs))

    return urlunsplit((scheme, host, path, query, ""))


def normalize_title(title: str) -> str:
    """标题归一：用于相似度比较，不用于展示。"""
    text = (title or "").lower()
    text = re.sub(r"[\s\u3000]+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_similarity(a: str, b: str) -> float:
    """0–100 的标题相似度（0–100 区间，与配置阈值同尺度）。"""
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return 0.0
    return max(
        fuzz.ratio(na, nb),
        fuzz.token_sort_ratio(na, nb),
        fuzz.partial_ratio(na, nb) if min(len(na), len(nb)) > 24 else 0.0,
    )


def is_same_title(a: str, b: str, threshold: int = 92) -> bool:
    return title_similarity(a, b) >= threshold


def is_duplicate_url(url_a: str, url_b: str) -> bool:
    return canonicalize_url(url_a) == canonicalize_url(url_b)

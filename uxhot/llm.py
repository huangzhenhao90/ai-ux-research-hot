"""LLM 客户端（OpenAI 兼容）。

零成本默认（计划 §2.3）：只有同时满足三个条件才会真的发请求——
  1. 构造时 `allow_calls=True`（脚本显式 `--execute`）
  2. 环境里有 `LLM_API_KEY`
  3. `MODEL_CALLS_ENABLED=true`

否则抛 `LLMCallsDisabled`，调用方应退回 dry-run。

本机注意：Clash TUN 把域名解析成 198.18.x.x 假 IP，且环境变量 `NO_PROXY` 含 `[::1]`，
httpx 默认 `trust_env=True` 会因它抛 `Invalid port: ':1]'`。所以这里显式构造 httpx 客户端
并自己读代理设置。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"

# 用哪个步骤的模型可以用这些变量覆盖（D8）
MODEL_ENV_BY_STEP = {
    "prefilter": "PREFILTER_MODEL",
    "score": "SCORE_MODEL",
    "write": "WRITE_MODEL",
}


class LLMError(RuntimeError):
    """调用失败。"""


class LLMCallsDisabled(LLMError):
    """安全阀没开或缺 key。调用方应退回 dry-run，而不是重试。"""


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """极简 .env 读取（不引入 python-dotenv 依赖）。

    只解析 `KEY=VALUE`，忽略空行与 `#` 开头的注释；已存在的环境变量优先，不覆盖。
    """
    env_path = path or DEFAULT_ENV_FILE
    values: dict[str, str] = {}
    if not env_path.is_file():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env(name: str, file_values: dict[str, str], default: str = "") -> str:
    """真实环境变量优先，其次 .env。"""
    return os.environ.get(name) or file_values.get(name) or default


@dataclass
class LLMConfig:
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    calls_enabled: bool = False
    model_by_step: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.calls_enabled and bool(self.api_key)

    def model_for(self, step: str) -> str:
        return self.model_by_step.get(step) or self.model

    def describe(self) -> str:
        """给日志用，**不输出 key**。"""
        key_state = "已设置" if self.api_key else "缺失"
        return (
            f"base_url={self.base_url} model={self.model} "
            f"api_key={key_state} calls_enabled={self.calls_enabled}"
        )


def load_llm_config(env_file: Path | None = None) -> LLMConfig:
    file_values = load_env_file(env_file)
    model_by_step = {
        step: _env(var, file_values)
        for step, var in MODEL_ENV_BY_STEP.items()
        if _env(var, file_values)
    }
    return LLMConfig(
        base_url=_env("LLM_BASE_URL", file_values, "https://api.deepseek.com"),
        api_key=_env("LLM_API_KEY", file_values),
        model=_env("LLM_MODEL", file_values, "deepseek-chat"),
        calls_enabled=_env("MODEL_CALLS_ENABLED", file_values, "false").lower() == "true",
        model_by_step=model_by_step,
    )


@dataclass
class CallRecord:
    """一次调用的审计记录（阶段 5 写进 data/runs/）。"""

    step: str
    model: str
    ok: bool
    prompt_chars: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 1
    error: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def build_http_client(timeout: float = 90.0) -> httpx.Client:
    """显式代理 + 关掉 trust_env，规避本机 NO_PROXY 的 `[::1]` 解析问题。"""
    proxy = (
        os.environ.get("https_proxy")
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("http_proxy")
        or os.environ.get("HTTP_PROXY")
    )
    kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
    if proxy:
        kwargs["proxy"] = proxy
    return httpx.Client(**kwargs)


class LLMClient:
    """OpenAI 兼容客户端，只要 JSON 输出。"""

    def __init__(
        self,
        config: LLMConfig | None = None,
        *,
        allow_calls: bool = False,
        env_file: Path | None = None,
    ) -> None:
        self.config = config or load_llm_config(env_file)
        self.allow_calls = allow_calls
        self.records: list[CallRecord] = []
        self._client = None

    # ── 安全阀 ────────────────────────────────────────────────────────

    def ensure_ready(self) -> None:
        if not self.allow_calls:
            raise LLMCallsDisabled(
                "未启用真实调用：脚本需要显式传 --execute（计划 §2.3）"
            )
        if not self.config.calls_enabled:
            raise LLMCallsDisabled(
                "未启用真实调用：环境变量 MODEL_CALLS_ENABLED 不是 true"
            )
        if not self.config.api_key:
            raise LLMCallsDisabled("未启用真实调用：缺少 LLM_API_KEY")

    def _sdk(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise LLMError("需要安装 openai 包") from exc
            self._client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                http_client=build_http_client(),
            )
        return self._client

    # ── 调用 ──────────────────────────────────────────────────────────

    def complete_json(
        self,
        prompt: str,
        *,
        step: str = "score",
        model: str | None = None,
        temperature: float | None = None,
        max_retries: int = 1,
    ) -> dict[str, Any]:
        """要一段 JSON。解析失败重试 `max_retries` 次（计划 §5.2 第 11 条）。

        `temperature` 默认不传：评分要求两次独立调用用模型默认温度。
        """
        self.ensure_ready()
        use_model = model or self.config.model_for(step)
        attempts = max_retries + 1
        last_error: str | None = None

        for attempt in range(1, attempts + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": use_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                }
                if temperature is not None:
                    kwargs["temperature"] = temperature

                resp = self._sdk().chat.completions.create(**kwargs)
                text = (resp.choices[0].message.content or "").strip()
                usage = getattr(resp, "usage", None)
                parsed = _parse_json(text)

                self.records.append(
                    CallRecord(
                        step=step,
                        model=use_model,
                        ok=True,
                        prompt_chars=len(prompt),
                        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        attempts=attempt,
                    )
                )
                return parsed

            except Exception as exc:  # noqa: BLE001 - 要把任何失败如实记录并重试
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt == attempts:
                    self.records.append(
                        CallRecord(
                            step=step,
                            model=use_model,
                            ok=False,
                            prompt_chars=len(prompt),
                            attempts=attempt,
                            error=last_error,
                        )
                    )

        raise LLMError(f"调用失败（{attempts} 次尝试）：{last_error}")

    # ── 审计 ──────────────────────────────────────────────────────────

    @property
    def call_count(self) -> int:
        return len(self.records)

    def usage_summary(self) -> dict[str, Any]:
        ok = [r for r in self.records if r.ok]
        return {
            "calls": len(self.records),
            "ok": len(ok),
            "failed": len(self.records) - len(ok),
            "prompt_tokens": sum(r.prompt_tokens for r in ok),
            "completion_tokens": sum(r.completion_tokens for r in ok),
            "total_tokens": sum(r.total_tokens for r in ok),
            "by_step": _count_by(self.records, "step"),
        }


def _count_by(records: list[CallRecord], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        key = getattr(r, attr)
        out[key] = out.get(key, 0) + 1
    return out


def _parse_json(text: str) -> dict[str, Any]:
    """容忍模型把 JSON 包在 ```json 里。"""
    if not text:
        raise LLMError("模型返回空内容")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = [ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError(f"返回内容不是合法 JSON：{cleaned[:200]}") from exc
    if not isinstance(parsed, dict):
        raise LLMError(f"返回的 JSON 顶层不是对象：{type(parsed).__name__}")
    return parsed

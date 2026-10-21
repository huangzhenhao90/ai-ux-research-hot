"""预算熔断（计划 §5.2 第 10 条，D9）。

每次运行 ≤ `perRunCalls`、每天 ≤ `perDayCalls`。超出即停：
**已完成的结果保留**，只是不再发起新的调用，并把本次用量写进运行审计。

日计数要跨运行累计（一天内会跑很多次），所以落盘到 `data/runs/`。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


class BudgetExceeded(RuntimeError):
    """调用额度用尽。调用方应停止后续模型调用，但保留已完成的结果。"""


@dataclass
class BudgetState:
    date: str                      # UTC 日期 YYYY-MM-DD
    calls: int = 0


@dataclass
class Budget:
    per_run_calls: int
    per_day_calls: int
    state_dir: Path
    now: datetime | None = None
    run_calls: int = 0
    day_calls: int = 0
    _events: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._reload_day()

    # ── 日期与落盘 ────────────────────────────────────────────────────

    @property
    def _now(self) -> datetime:
        return (self.now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    @property
    def today(self) -> str:
        return self._now.strftime("%Y-%m-%d")

    @property
    def state_path(self) -> Path:
        return self.state_dir / "budget.json"

    def _reload_day(self) -> None:
        """载入当天已用次数。日期变了就归零（新的一天重新计数）。"""
        state = self._read_state()
        if state is not None and state.date == self.today:
            self.day_calls = state.calls
        else:
            self.day_calls = 0

    def _read_state(self) -> BudgetState | None:
        if not self.state_path.is_file():
            return None
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return BudgetState(date=str(raw["date"]), calls=int(raw["calls"]))
        except Exception:  # noqa: BLE001 - 状态坏了就当没有，不要卡住整次运行
            return None

    def save(self) -> None:
        payload = {"date": self.today, "calls": self.day_calls}
        self.state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ── 计数 ──────────────────────────────────────────────────────────

    @property
    def run_remaining(self) -> int:
        return max(0, self.per_run_calls - self.run_calls)

    @property
    def day_remaining(self) -> int:
        return max(0, self.per_day_calls - self.day_calls)

    @property
    def remaining(self) -> int:
        """还能调几次：取单次与当天两个上限里更紧的那个。"""
        return min(self.run_remaining, self.day_remaining)

    def can_call(self, n: int = 1) -> bool:
        return n <= self.remaining

    def charge(self, n: int = 1) -> None:
        """记账。超限就抛 BudgetExceeded，并且**不**记账。"""
        if n > self.remaining:
            reason = (
                "本次运行额度用尽" if self.run_remaining <= self.day_remaining
                else "当日额度用尽"
            )
            self._events.append(
                f"{reason}：本次已用 {self.run_calls}/{self.per_run_calls}，"
                f"当日已用 {self.day_calls}/{self.per_day_calls}"
            )
            raise BudgetExceeded(self._events[-1])
        self.run_calls += n
        self.day_calls += n

    def snapshot(self) -> dict:
        return {
            "perRunCalls": self.per_run_calls,
            "perDayCalls": self.per_day_calls,
            "runCalls": self.run_calls,
            "dayCalls": self.day_calls,
            "remaining": self.remaining,
            "exhausted": self.remaining == 0,
            "events": list(self._events),
        }

    def describe(self) -> str:
        return (
            f"预算：本次 {self.run_calls}/{self.per_run_calls}，"
            f"当日 {self.day_calls}/{self.per_day_calls}，剩余 {self.remaining}"
        )

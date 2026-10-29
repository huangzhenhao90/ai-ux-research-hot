"use client";

import { useEffect, useState } from "react";

import { track } from "@/lib/track";

import { IconMonitor, IconMoon, IconSun } from "./icons";

type Choice = "dark" | "system" | "light";

/** 与 app/layout.tsx 里首屏脚本读的是同一个键。 */
export const THEME_STORAGE_KEY = "uxhot-theme";

const OPTIONS: { key: Choice; label: string; icon: React.ReactNode }[] = [
  { key: "dark", label: "深色", icon: <IconMoon size={14} /> },
  { key: "system", label: "跟随系统", icon: <IconMonitor size={14} /> },
  { key: "light", label: "浅色", icon: <IconSun size={14} /> },
];

/**
 * 三档外观开关：深色 / 跟随系统 / 浅色，白色滑块停在当前档。
 *
 * 跟随系统时不写 `data-theme`，由 CSS 的 `prefers-color-scheme` 决定；
 * 手动选了深浅色就写进 localStorage，并在 `<html data-theme>` 上覆盖。
 * 首屏由 layout 里的内联脚本先套上，避免闪一下。
 */
export function ThemeSwitch({ className = "" }: { className?: string }) {
  const [current, setCurrent] = useState<Choice>("system");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (saved === "light" || saved === "dark") setCurrent(saved);
    } catch {
      // 隐私模式等读不了存储：保持跟随系统
    }
  }, []);

  function choose(next: Choice) {
    setCurrent(next);
    track("theme", { theme: next });
    const root = document.documentElement;
    try {
      if (next === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
      else window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // 存不了也照样切换本次显示
    }
    if (next === "system") delete root.dataset.theme;
    else root.dataset.theme = next;
  }

  const index = OPTIONS.findIndex((o) => o.key === current);

  return (
    <div role="radiogroup" aria-label="外观" className={`theme-switch ${className}`}>
      <span
        aria-hidden="true"
        className="theme-switch__thumb"
        style={{ transform: `translateX(${index * 100}%)` }}
      />
      {OPTIONS.map((o) => (
        <button
          key={o.key}
          type="button"
          role="radio"
          aria-checked={current === o.key}
          title={o.label}
          onClick={() => choose(o.key)}
          className="theme-switch__option"
        >
          {o.icon}
          <span className="sr-only">{o.label}</span>
        </button>
      ))}
    </div>
  );
}

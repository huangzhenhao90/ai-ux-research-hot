"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

const STORAGE_KEY = "uxhot-theme";

/**
 * 深浅色切换。
 *
 * 默认跟随系统（CSS 里的 `prefers-color-scheme`）；用户手动切换后写 localStorage，
 * 并在 `<html data-theme>` 上覆盖。用 `useEffect` 读，避免服务端渲染与客户端不一致。
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") {
      setTheme(saved);
      document.documentElement.dataset.theme = saved;
    }
  }, []);

  function toggle() {
    const next: Theme =
      theme ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light") === "dark"
        ? "light"
        : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem(STORAGE_KEY, next);
  }

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggle}
      aria-label="切换深浅色"
      title="切换深浅色"
    >
      {theme === "dark" ? "浅色" : theme === "light" ? "深色" : "配色"}
    </button>
  );
}

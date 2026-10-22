"use client";

import { useMemo, useState } from "react";

import { ItemCard } from "@/components/ItemCard";
import type { PublicItem } from "@/lib/types";

/** 首屏渲染条数；剩下的点「加载更多」再展开。 */
const PAGE_SIZE = 100;

/**
 * 全部动态的筛选 + 分批展开。
 *
 * 静态导出没有后端，条目全部由服务端在构建期一次性传进来，筛选与分页都在浏览器
 * 内存里完成，不发任何请求。
 *
 * `ItemCard` 可以在这里直接用：它只依赖 `lib/format.ts`（纯函数），
 * 不碰 `lib/data.ts`（那个 import 了 node:fs，链进来会让客户端打包失败）。
 */
export function AllClient({
  items,
  categories,
  reasonLabel,
}: {
  items: PublicItem[];
  categories: { key: string; label: string }[];
  reasonLabel: string;
}) {
  // null = 不筛选
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [visible, setVisible] = useState(PAGE_SIZE);

  /** 每个分类在当前列表里的实际条数（以传进来的条目为准，避免和索引对不上）。 */
  const counts = useMemo(() => {
    const map = new Map<string, number>();
    let uncategorized = 0;
    for (const item of items) {
      if (item.category) {
        map.set(item.category, (map.get(item.category) ?? 0) + 1);
      } else {
        uncategorized += 1;
      }
    }
    return { map, uncategorized };
  }, [items]);

  const filtered = useMemo(() => {
    if (activeKey === null) return items;
    if (activeKey === "__none__") return items.filter((item) => !item.category);
    return items.filter((item) => item.category === activeKey);
  }, [items, activeKey]);

  const shown = filtered.slice(0, visible);
  const rest = filtered.length - shown.length;
  const activeLabel =
    activeKey === null
      ? null
      : activeKey === "__none__"
        ? "未分类"
        : (categories.find((category) => category.key === activeKey)?.label ??
          activeKey);

  function select(key: string | null) {
    setActiveKey(key);
    setVisible(PAGE_SIZE);
  }

  return (
    <>
      <div className="filter-bar" role="group" aria-label="按分类筛选">
        <button
          type="button"
          className="filter-chip"
          aria-pressed={activeKey === null}
          onClick={() => select(null)}
        >
          全部 {items.length}
        </button>
        {categories.map((category) => (
          <button
            key={category.key}
            type="button"
            className="filter-chip"
            aria-pressed={activeKey === category.key}
            onClick={() => select(category.key)}
          >
            {category.label} {counts.map.get(category.key) ?? 0}
          </button>
        ))}
        {/* 首次导入的历史条目还没走结构化，没有分类；给它们一个入口，别让人以为丢了 */}
        {counts.uncategorized > 0 ? (
          <button
            type="button"
            className="filter-chip"
            aria-pressed={activeKey === "__none__"}
            onClick={() => select("__none__")}
          >
            未分类 {counts.uncategorized}
          </button>
        ) : null}
      </div>

      <p
        className="section__count"
        style={{ marginBottom: "0.75rem" }}
        aria-live="polite"
      >
        {activeLabel === null
          ? `全部 ${filtered.length} 条`
          : `${activeLabel} ${filtered.length} 条`}
        {rest > 0 ? ` · 已显示 ${shown.length} 条` : ""}
      </p>

      {shown.length === 0 ? (
        <p className="empty">这个分类下还没有收录条目。</p>
      ) : (
        <div className="card-list">
          {shown.map((item) => (
            <ItemCard key={item.id} item={item} reasonLabel={reasonLabel} />
          ))}
        </div>
      )}

      {rest > 0 ? (
        <div style={{ marginTop: "1.25rem", textAlign: "center" }}>
          <button
            type="button"
            className="filter-chip"
            style={{ padding: "0.45rem 1.1rem", fontSize: "0.9375rem" }}
            onClick={() => setVisible((value) => value + PAGE_SIZE)}
          >
            加载更多（还有 {rest} 条）
          </button>
        </div>
      ) : null}
    </>
  );
}

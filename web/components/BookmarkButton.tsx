"use client";

import type { FavInput } from "@/lib/favorites";
import { toggleFavorite, useFavorites, useIsFavorite } from "@/lib/favorites-store";
import { track } from "@/lib/track";

import { IconBookmark } from "./icons";

/**
 * 书签按钮：卡片右上角的小图标，详情页顶部的「收藏」胶囊（`variant="pill"`）。
 *
 * 收藏存在读者自己的浏览器里（见 `lib/favorites-store.ts`）。服务端渲染与水合时一律显示「未收藏」，
 * 水合之后再按本地存储变成实心，所以不会有水合不一致。
 *
 * 按钮放在卡片头部的链接旁，要浮在「整张卡片可点」的标题链接铺层之上（`card__raise`），
 * 点它不能同时跳进详情页。
 */
export function BookmarkButton({
  entry,
  where,
  variant = "icon",
}: {
  entry: FavInput;
  /** 埋点用：在哪里点的 */
  where: "card" | "detail" | "favorites";
  variant?: "icon" | "pill";
}) {
  const saved = useIsFavorite(entry.kind, entry.id);

  function onClick(event: React.MouseEvent) {
    // 卡片本身是链接铺层的一部分，防止点书签时顺带触发它
    event.stopPropagation();
    const now = toggleFavorite(entry);
    track("bookmark", { action: now ? "add" : "remove", kind: entry.kind, where });
  }

  const label = saved ? "取消收藏" : "收藏";
  return (
    <button
      type="button"
      className={`bookmark bookmark--${variant} card__raise${saved ? " is-saved" : ""}`}
      aria-pressed={saved}
      aria-label={`收藏：${entry.title}`}
      title={label}
      onClick={onClick}
    >
      <IconBookmark size={variant === "pill" ? 15 : 18} fill={saved ? "currentColor" : "none"} />
      {variant === "pill" ? <span>{saved ? "已收藏" : "收藏"}</span> : null}
    </button>
  );
}

/** 侧栏「收藏夹」旁的数字；没有收藏时不显示。 */
export function FavCount() {
  const count = useFavorites().length;
  return count > 0 ? <span className="side-link__count num">{count}</span> : null;
}

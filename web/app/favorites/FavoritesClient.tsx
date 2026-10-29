"use client";

import Link from "next/link";
import { useMemo, useRef, useState } from "react";

import { BookmarkButton } from "@/components/BookmarkButton";
import { IconDownload, IconExternal, IconSearch, IconUpload } from "@/components/icons";
import { FAV_KINDS, type FavEntry, type FavKind, favHref } from "@/lib/favorites";
import {
  clearFavorites,
  exportFavorites,
  importFavorites,
  useFavorites,
  useHydrated,
  usePersistFailed,
} from "@/lib/favorites-store";
import { formatDate } from "@/lib/format";
import { track } from "@/lib/track";

type Tab = "all" | FavKind;

const MAX_IMPORT_BYTES = 2 * 1024 * 1024;

function matchesQuery(entry: FavEntry, query: string): boolean {
  if (!query) return true;
  const text = [entry.title, entry.subtitle, ...entry.tags].join(" ").toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => text.includes(term));
}

/**
 * 收藏夹：按类别看、搜索、移出、导出 / 导入备份、清空。
 *
 * 数据全在本地（`lib/favorites-store.ts`）。水合之前显示「正在读取」而不是「还没有收藏」，
 * 免得有收藏的人每次打开都先闪一下空状态。
 */
export function FavoritesClient({ live }: { live: Record<FavKind, string[]> }) {
  const entries = useFavorites();
  const hydrated = useHydrated();
  const persistFailed = usePersistFailed();
  const [tab, setTab] = useState<Tab>("all");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const liveIds = useMemo(
    () => ({
      item: new Set(live.item),
      social: new Set(live.social),
      campus: new Set(live.campus),
    }),
    [live],
  );

  const counts: Record<Tab, number> = { all: entries.length, item: 0, social: 0, campus: 0 };
  for (const entry of entries) counts[entry.kind] += 1;

  const shown = entries.filter((entry) => (tab === "all" || entry.kind === tab) && matchesQuery(entry, query.trim()));

  function onExport() {
    const url = URL.createObjectURL(new Blob([exportFavorites()], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `urhot-favorites-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    track("favorites", { action: "export" });
    setNotice(`已导出 ${entries.length} 条收藏。`);
  }

  async function onImport(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_IMPORT_BYTES) {
      setNotice("这个文件太大了，不像是从这里导出的收藏备份。");
      return;
    }
    const { added, skipped } = importFavorites(await file.text());
    track("favorites", { action: "import" });
    setNotice(
      added === 0 && skipped === 0
        ? "没有读到有效的收藏，请选从这里导出的 .json 文件。"
        : `导入了 ${added} 条新收藏${skipped ? `，${skipped} 条已经在收藏夹里` : ""}。`,
    );
  }

  function onClear() {
    if (!window.confirm(`清空全部 ${entries.length} 条收藏？这个操作不能撤销。`)) return;
    clearFavorites();
    track("favorites", { action: "clear" });
    setNotice("已清空。");
  }

  const tabs: { key: Tab; label: string }[] = [{ key: "all", label: "全部" }, ...FAV_KINDS.map((k) => ({ key: k.kind, label: k.label }))];

  return (
    <>
      {persistFailed ? (
        <p className="callout callout--warn" role="alert">
          这个浏览器不让网页保存数据（可能开着无痕模式），收藏在关掉页面后会丢失。可以先「导出」留一份。
        </p>
      ) : null}

      <div className="feed-bar">
        <div className="pill-tabs" role="group" aria-label="按类别筛选">
          {tabs.map((option) => (
            <button
              key={option.key}
              type="button"
              className="pill-tabs__tab"
              aria-pressed={tab === option.key}
              onClick={() => {
                setTab(option.key);
                track("filter", { tab: "favorites", by: "kind" });
              }}
            >
              {option.label} <span className="num">{hydrated ? counts[option.key] : 0}</span>
            </button>
          ))}
        </div>
        <div className="feed-bar__tools">
          <label className="search-box">
            <IconSearch size={15} />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜收藏的标题、公司…"
              aria-label="搜索收藏"
              className="search-box__input"
            />
          </label>
        </div>
      </div>

      <p className="section__count campus-count" aria-live="polite">
        <span>
          共 <span className="num">{hydrated ? shown.length : 0}</span> 条
        </span>
        <button type="button" className="link-button" onClick={onExport} disabled={entries.length === 0}>
          <IconDownload size={13} /> 导出
        </button>
        <button type="button" className="link-button" onClick={() => fileInput.current?.click()}>
          <IconUpload size={13} /> 导入
        </button>
        {entries.length > 0 ? (
          <button type="button" className="link-button link-button--danger" onClick={onClear}>
            清空
          </button>
        ) : null}
        {notice ? <span role="status">{notice}</span> : null}
        <input
          ref={fileInput}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(event) => {
            void onImport(event.target.files?.[0]);
            event.target.value = "";
          }}
        />
      </p>

      {!hydrated ? (
        <p className="empty">正在读取收藏…</p>
      ) : entries.length === 0 ? (
        <p className="empty">
          还没有收藏。
          <br />
          在 <Link href="/">精选</Link>、<Link href="/social/">用研社招</Link>、
          <Link href="/campus/">用研校招</Link> 的卡片右上角点书签，就会出现在这里。
        </p>
      ) : shown.length === 0 ? (
        <p className="empty">没有符合条件的收藏，换个类别或关键词试试。</p>
      ) : (
        <div className="card-list">
          {shown.map((entry) => (
            <FavCard key={entry.key} entry={entry} live={liveIds[entry.kind].has(entry.id)} />
          ))}
        </div>
      )}
    </>
  );
}

function FavCard({ entry, live }: { entry: FavEntry; live: boolean }) {
  const kind = FAV_KINDS.find((k) => k.kind === entry.kind)!;
  const isItem = entry.kind === "item";
  const external = entry.url ? (
    <a href={entry.url} target="_blank" rel="noopener noreferrer nofollow" data-track="outbound" data-track-kind="favorite_link" data-track-tab="favorites">
      {entry.title}
    </a>
  ) : null;

  return (
    <article className="card card--item">
      <header className="card__head">
        <span className="badge badge--accent">{kind.label}</span>
        <span className="card__source">{entry.subtitle}</span>
        {entry.tags.map((tag) => (
          <span key={tag} className="badge">
            {tag}
          </span>
        ))}
        {live ? null : <span className="badge badge--gone">{isItem ? "已移出站点" : "已下架"}</span>}
        <span className="card__actions">
          {entry.url ? (
            <a
              href={entry.url}
              target="_blank"
              rel="noopener noreferrer nofollow"
              className="card__origin card__raise"
              title={isItem ? "打开原文" : "打开官方岗位页"}
              data-track="outbound"
              data-track-kind="favorite_link"
              data-track-tab="favorites"
            >
              {isItem ? "原文" : "官方页面"}
              <IconExternal size={12} />
            </a>
          ) : null}
          <BookmarkButton entry={entry} where="favorites" />
        </span>
      </header>

      <h3 className="card__title">
        {live ? (
          <Link href={favHref(entry.kind, entry.id)} className="card__link">
            {entry.title}
          </Link>
        ) : (
          (external ?? entry.title)
        )}
      </h3>

      <p className="card__meta">
        <span>收藏于 {formatDate(entry.savedAt)}</span>
        {live ? null : (
          <span>
            {isItem ? "这条内容已不在站内。" : "站内详情页已下架，岗位可能已经关闭，请以官网为准。"}
          </span>
        )}
      </p>
    </article>
  );
}

/**
 * 收藏的本地存储与 hooks（DECISIONS D19）。只给客户端组件用。
 *
 * 同一页上有几十张卡片、每张一个书签按钮，另一个标签页里改了收藏也要同步，
 * 所以用一个外部 store：读一次 localStorage 缓存起来，写入时更新缓存并通知所有订阅者
 * （`useSyncExternalStore`）。服务端渲染与水合时一律是「没有收藏」，水合之后才读本地存储，
 * 所以不会有水合不一致。
 *
 * 数据结构与校验在 `favorites.ts`；这里读出来的、导入进来的数据一律当不可信的、过一遍校验。
 */

import { useSyncExternalStore } from "react";

import {
  type FavEntry,
  type FavInput,
  type FavKind,
  MAX_ENTRIES,
  favKey,
  parseEntries,
  sanitizeEntry,
} from "./favorites";

export const FAV_STORAGE_KEY = "uxhot-favorites";

const EMPTY: FavEntry[] = [];
let cache: FavEntry[] | null = null;
let keys: Set<string> = new Set();
let persistFailed = false;
const listeners = new Set<() => void>();

function load(): FavEntry[] {
  if (cache) return cache;
  let entries = EMPTY;
  try {
    const raw = window.localStorage.getItem(FAV_STORAGE_KEY);
    if (raw) entries = parseEntries(raw);
  } catch {
    // 读不了存储（隐私模式等）：当作没有收藏
  }
  cache = entries;
  keys = new Set(entries.map((entry) => entry.key));
  return cache;
}

function commit(next: FavEntry[]): void {
  cache = next;
  keys = new Set(next.map((entry) => entry.key));
  try {
    window.localStorage.setItem(FAV_STORAGE_KEY, JSON.stringify(next));
    persistFailed = false;
  } catch {
    // 存不下（隐私模式、配额）：本次浏览仍然有效，收藏夹页面会提示刷新后会丢
    persistFailed = true;
  }
  listeners.forEach((notify) => notify());
}

function onStorage(event: StorageEvent): void {
  if (event.key !== null && event.key !== FAV_STORAGE_KEY) return;
  cache = null;
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void): () => void {
  if (listeners.size === 0) window.addEventListener("storage", onStorage);
  listeners.add(notify);
  return () => {
    listeners.delete(notify);
    if (listeners.size === 0) window.removeEventListener("storage", onStorage);
  };
}

// ── 对外的操作 ───────────────────────────────────────────────────────────

/** 收藏 / 取消收藏；返回操作之后是不是已收藏。 */
export function toggleFavorite(input: FavInput): boolean {
  const key = favKey(input.kind, input.id);
  const current = load();
  if (keys.has(key)) {
    commit(current.filter((entry) => entry.key !== key));
    return false;
  }
  const entry = sanitizeEntry({ ...input, savedAt: new Date().toISOString() });
  if (!entry) return false;
  commit([entry, ...current]);
  return true;
}

export function removeFavorite(key: string): void {
  commit(load().filter((entry) => entry.key !== key));
}

export function clearFavorites(): void {
  commit(EMPTY);
}

export function exportFavorites(): string {
  return JSON.stringify({ app: "urhot", version: 1, exportedAt: new Date().toISOString(), entries: load() }, null, 2);
}

/** 合并导入：已有的收藏保持不动（保留原来的收藏时间），只加新的。 */
export function importFavorites(json: string): { added: number; skipped: number } {
  const incoming = parseEntries(json);
  const current = load();
  const fresh = incoming.filter((entry) => !keys.has(entry.key));
  if (fresh.length > 0) {
    commit([...current, ...fresh].sort((a, b) => Date.parse(b.savedAt) - Date.parse(a.savedAt)).slice(0, MAX_ENTRIES));
  }
  return { added: fresh.length, skipped: incoming.length - fresh.length };
}

// ── hooks ────────────────────────────────────────────────────────────────

export function useFavorites(): FavEntry[] {
  return useSyncExternalStore(subscribe, load, () => EMPTY);
}

export function useIsFavorite(kind: FavKind, id: string): boolean {
  const key = favKey(kind, id);
  return useSyncExternalStore(
    subscribe,
    () => {
      load(); // 另一个标签页改过收藏时缓存被清掉，先重读再查
      return keys.has(key);
    },
    () => false,
  );
}

/** 最近一次写入有没有失败（隐私模式等存不住）。 */
export function usePersistFailed(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => persistFailed,
    () => false,
  );
}

/** 水合之后才是 true：收藏夹页面据此区分「还没读到」和「真的是空的」。 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}


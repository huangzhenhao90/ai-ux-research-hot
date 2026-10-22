"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

/** 服务端整理好的展示条目（见 app/search/page.tsx）。 */
export interface SearchEntry {
  id: string;
  title: string;
  originalTitle: string | null;
  summary: string | null;
  tags: string[];
  entities: string[];
  categoryLabel: string | null;
  sourceName: string;
  time: string;
}

/** 命中过多时只渲染前这么多条，提示细化关键词。 */
const MAX_RESULTS = 100;

/** 把一条记录的检索字段拼成一个可 `includes` 的小写串。 */
function haystack(entry: SearchEntry): string {
  return [
    entry.title,
    entry.originalTitle ?? "",
    entry.summary ?? "",
    entry.tags.join(" "),
    entry.entities.join(" "),
    entry.sourceName,
  ]
    .join(" ")
    .toLowerCase();
}

/**
 * 本地搜索框。
 *
 * 纯浏览器内过滤：不请求网络、不改 URL、不用路由。空白分隔的多个关键词之间是
 * 「同时包含」（AND）的关系，全部不区分大小写。
 */
export function SearchClient({ items }: { items: SearchEntry[] }) {
  const [query, setQuery] = useState("");

  // 预先把全部记录转成检索串，输入时只做字符串比较
  const indexed = useMemo(
    () => items.map((entry) => ({ entry, text: haystack(entry) })),
    [items],
  );

  const terms = useMemo(
    () =>
      query
        .toLowerCase()
        .split(/\s+/)
        .filter((term) => term.length > 0),
    [query],
  );

  const matched = useMemo(() => {
    if (terms.length === 0) return [];
    return indexed
      .filter(({ text }) => terms.every((term) => text.includes(term)))
      .map(({ entry }) => entry);
  }, [indexed, terms]);

  const shown = matched.slice(0, MAX_RESULTS);
  const keyword = query.trim();

  return (
    <>
      <div>
        <label htmlFor="search-q" className="section__count">
          关键词
        </label>
        <input
          id="search-q"
          className="search-input"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="例如：合成用户 / NPS / 可用性测试 / Dovetail"
          autoComplete="off"
          spellCheck={false}
          aria-describedby="search-hint"
        />
        <p id="search-hint" className="section__count" style={{ marginTop: "0.5rem" }}>
          多个关键词用空格分隔（同时命中才显示）；不区分大小写。
        </p>
      </div>

      <p
        className="section__count"
        style={{ marginTop: "1.25rem" }}
        aria-live="polite"
      >
        {terms.length === 0 ? "" : `命中 ${matched.length} 条`}
      </p>

      {terms.length === 0 ? (
        <p className="empty">
          输入关键词开始搜索。
          <br />
          可以搜中文标题、英文原标题、摘要、标签、实体名和来源名称。
        </p>
      ) : matched.length === 0 ? (
        <p className="empty">
          没有匹配「{keyword}」的条目。
          <br />
          试试更短的关键词，或者去
          <Link href="/all/">全部动态</Link>
          里按分类翻。
        </p>
      ) : (
        <>
          <div className="card-list">
            {shown.map((entry) => (
              <article className="card" key={entry.id}>
                <h3 className="card__title">
                  <Link href={`/item/${entry.id}/`}>{entry.title}</Link>
                </h3>

                {entry.originalTitle ? (
                  <p className="section__count" lang="en" style={{ marginTop: "0.2rem" }}>
                    {entry.originalTitle}
                  </p>
                ) : null}

                {entry.summary ? (
                  <p className="card__summary">{entry.summary}</p>
                ) : null}

                {entry.tags.length > 0 ? (
                  <div className="tag-row">
                    {entry.tags.slice(0, 6).map((tag) => (
                      <span key={tag} className="badge badge--plain">
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}

                <div className="card__meta">
                  {entry.categoryLabel ? <span>{entry.categoryLabel}</span> : null}
                  <span>{entry.sourceName}</span>
                  {entry.time ? <time>{entry.time}</time> : null}
                </div>
              </article>
            ))}
          </div>

          {matched.length > shown.length ? (
            <p className="section__count" style={{ marginTop: "1rem" }}>
              命中太多，只显示前 {MAX_RESULTS} 条；再输入一个关键词缩小范围。
            </p>
          ) : null}
        </>
      )}
    </>
  );
}

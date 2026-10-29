import type { Metadata } from "next";

import { PageShell } from "@/components/PageShell";
import { getCampus, getSocial, listItemIds } from "@/lib/data";
import type { FavKind } from "@/lib/favorites";

import { FavoritesClient } from "./FavoritesClient";

export const metadata: Metadata = {
  title: "收藏夹",
  description: "你收藏的资讯、社招岗位和校招岗位。收藏只保存在你当前使用的浏览器里。",
};

/** 中文整段写成一行字符串：JSX 里换行会折成一个空格，中文标点后面多一个空格不好看。 */
const INTRO =
  "在资讯、社招、校招的卡片右上角点书签，就会收进这里。收藏只保存在你当前使用的浏览器里（不登录、不上传）；换设备或清理浏览器数据前，可以先导出备份。";

/**
 * 收藏夹。
 *
 * 收藏存在读者自己浏览器的 localStorage 里（DECISIONS D19），页面本身是静态的；
 * 构建期只把「现在站内还有哪些条目 / 岗位」告诉客户端，用来标出已经下架的收藏。
 */
export default function FavoritesPage() {
  const live: Record<FavKind, string[]> = {
    item: listItemIds(),
    social: getSocial()?.jobs.map((job) => job.id) ?? [],
    campus: getCampus()?.jobs.map((job) => job.id) ?? [],
  };

  return (
    <PageShell current="/favorites/">
      <div className="page-head">
        <h1>收藏夹</h1>
        <p className="page-head__desc">{INTRO}</p>
      </div>

      <FavoritesClient live={live} />
    </PageShell>
  );
}

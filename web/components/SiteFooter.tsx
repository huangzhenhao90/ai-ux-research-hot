import Link from "next/link";

import { getSite } from "@/lib/data";

/** `narrow` 与 PageShell 一致：阅读页的站脚跟正文栏同宽、居中对齐。 */
export function SiteFooter({ narrow = false }: { narrow?: boolean }) {
  const site = getSite();

  return (
    <footer className={narrow ? "site-footer site-footer--narrow" : "site-footer"}>
      <span>
        {site.name} · {site.alias}
        {site.byline ? ` · ${site.byline}` : ""}
      </span>
      <Link href="/about/">关于</Link>
      <Link href="/about/#sources">信源</Link>
      <a href={`${site.basePath}/rss.xml`} data-track="rss" data-track-where="footer">
        RSS
      </a>
      <span>
        信源内容版权归各发布方所有；动态只展示摘要与原文链接，岗位描述转自企业官网公开页面或来源平台。
      </span>
    </footer>
  );
}

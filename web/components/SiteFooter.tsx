import Link from "next/link";

import { getSite } from "@/lib/data";

export function SiteFooter() {
  const site = getSite();

  return (
    <footer className="site-footer">
      <span>
        {site.name} · {site.alias}
      </span>
      <Link href="/about/">关于</Link>
      <Link href="/about/#sources">信源</Link>
      <a href={`${site.basePath}/rss.xml`}>RSS</a>
      <span>信源内容版权归各发布方所有，本站只展示摘要与原文链接。</span>
    </footer>
  );
}

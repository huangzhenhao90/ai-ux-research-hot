import type { Metadata } from "next";

import { Analytics } from "@/components/Analytics";
import { getSite } from "@/lib/data";

import "./globals.css";

const site = getSite();

/**
 * 首屏前套上用户手动选过的深浅色，避免先按系统配色画一帧再跳。
 * 键名与 components/ThemeSwitch.tsx 的 THEME_STORAGE_KEY 一致。
 */
const THEME_SCRIPT = `try{var t=localStorage.getItem("uxhot-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export const metadata: Metadata = {
  title: {
    default: site.homeTitle,
    template: `%s · ${site.name}`,
  },
  description: site.description,
  metadataBase: new URL(site.siteUrl),
  alternates: {
    types: {
      // 只给相对路径：Next 会自己拼上 basePath，写全路径会重复一次
      "application/rss+xml": "/rss.xml",
    },
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // data-theme 由下面的内联脚本在首屏前写入，服务端渲染时没有，所以要放过这处不一致
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}

import type { Metadata } from "next";

import { getSite } from "@/lib/data";

import "./globals.css";

const site = getSite();

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
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

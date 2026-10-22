import Link from "next/link";

import { getSite } from "@/lib/data";

import { ThemeToggle } from "./ThemeToggle";

/**
 * 导航项。`exact` 用于首页，避免所有页面都命中 `/`。
 */
const NAV = [
  { href: "/", label: "精选", exact: true },
  { href: "/all/", label: "全部动态" },
  { href: "/daily/", label: "日报" },
  { href: "/weekly/", label: "周报" },
  { href: "/topics/", label: "主题" },
  { href: "/search/", label: "搜索" },
  { href: "/about/", label: "关于" },
];

export function SiteHeader({ current }: { current?: string }) {
  const site = getSite();

  return (
    <header className="site-header">
      <div className="wrap site-header__inner">
        <Link href="/" className="logo">
          {site.name}
          <span className="logo__alias">{site.alias}</span>
        </Link>

        <nav className="site-nav" aria-label="主导航">
          {NAV.map((item) => {
            const active = item.exact
              ? current === item.href
              : current?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <ThemeToggle />
      </div>
    </header>
  );
}

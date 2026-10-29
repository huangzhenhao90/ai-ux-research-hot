import Link from "next/link";

import { getSite } from "@/lib/data";

import { Byline, Wordmark } from "./Brand";
import { FavCount } from "./BookmarkButton";
import {
  IconBolt,
  IconBookmark,
  IconBriefcase,
  IconCap,
  IconGrid,
  IconHeart,
  IconList,
  IconRss,
  IconSearch,
  type Icon,
} from "./icons";
import { ThemeSwitch } from "./ThemeSwitch";

interface NavItem {
  href: string;
  label: string;
  icon: Icon;
  /** 首页要精确匹配，否则所有页面都会命中 `/`。 */
  exact?: boolean;
}

const SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "内容",
    items: [
      { href: "/", label: "精选", icon: IconBolt, exact: true },
      { href: "/all/", label: "全部动态", icon: IconList },
      { href: "/topics/", label: "主题", icon: IconGrid },
      { href: "/search/", label: "搜索", icon: IconSearch },
    ],
  },
  {
    title: "求职",
    items: [
      { href: "/campus/", label: "用研校招", icon: IconCap },
      { href: "/social/", label: "用研社招", icon: IconBriefcase },
    ],
  },
  {
    title: "我的",
    items: [{ href: "/favorites/", label: "收藏夹", icon: IconBookmark }],
  },
  {
    title: "更多",
    items: [{ href: "/about/", label: "关于", icon: IconHeart }],
  },
];

function isActive(item: NavItem, current?: string): boolean {
  if (!current) return false;
  return item.exact ? current === item.href : current.startsWith(item.href);
}

/**
 * 把别名拆成「词」：连续的西文与数字算一个词，其余字符（中文、标点）逐个拆开，空白丢掉。
 * 侧栏里别名要和上面的字标左右对齐，做法是让这些词在一行里均匀摊开（见 `.sidebar__alias`）。
 */
function spreadWords(text: string): string[] {
  return text.match(/[A-Za-z0-9][A-Za-z0-9._'’+-]*|[^\sA-Za-z0-9]/gu) ?? [];
}

/**
 * 桌面左侧栏（≥ 961px）：标志与字标、别名、出品方署名、分组导航、RSS 与外观开关。
 *
 * `current` 是当前页的路由路径（如 `/all/`），用来点亮对应入口。
 */
export function Sidebar({ current }: { current?: string }) {
  const site = getSite();

  return (
    <aside className="sidebar">
      <div className="sidebar__lockup">
        <Link href="/" className="sidebar__brand" aria-label={`${site.name} 首页`}>
          <Wordmark />
        </Link>
        {/* 摊开后的字是给眼睛看的；读屏软件读下面那份完整的别名 */}
        <span className="sidebar__alias">
          <span className="sr-only">{site.alias}</span>
          {spreadWords(site.alias).map((word, index) => (
            <span key={index} aria-hidden="true">
              {word}
            </span>
          ))}
        </span>
      </div>
      <span className="sidebar__byline">
        <Byline />
      </span>

      <nav className="sidebar__nav" aria-label="主导航">
        {SECTIONS.map((section) => (
          <div key={section.title}>
            <div className="sidebar__section">{section.title}</div>
            <div className="sidebar__items">
              {section.items.map((item) => {
                const active = isActive(item, current);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="side-link"
                    aria-current={active ? "page" : undefined}
                  >
                    <span className="side-link__icon">
                      <Icon size={17} />
                    </span>
                    {item.label}
                    {item.href === "/favorites/" ? <FavCount /> : null}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      <div className="sidebar__foot">
        <a
          href={`${site.basePath}/rss.xml`}
          className="pill-button"
          data-track="rss"
          data-track-where="sidebar"
        >
          <IconRss size={14} />
          RSS 订阅
        </a>
        <ThemeSwitch />
      </div>
    </aside>
  );
}

/** 手机与窄屏（< 961px）：顶栏放字标、署名与外观开关，下面一行可横向滑动的导航。 */
export function PhoneBar({ current }: { current?: string }) {
  const site = getSite();
  const items = SECTIONS.flatMap((section) => section.items);

  return (
    <header className="phonebar">
      <div className="phonebar__top">
        <Link href="/" className="phonebar__brand" aria-label={`${site.name} 首页`}>
          <Wordmark small />
          <Byline size="sm" />
        </Link>
        <ThemeSwitch className="theme-switch--compact" />
      </div>
      <nav className="phonebar__nav" aria-label="主导航">
        {items.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive(item, current) ? "page" : undefined}
          >
            {item.label}
            {item.href === "/favorites/" ? <FavCount /> : null}
          </Link>
        ))}
      </nav>
    </header>
  );
}

import { PhoneBar, Sidebar } from "./Sidebar";
import { SiteFooter } from "./SiteFooter";

/**
 * 页面外壳：桌面左侧栏 + 主区；手机上侧栏收成顶栏。
 *
 * `current` 用于高亮导航，传路由路径（如 `/all/`）。
 * `narrow` 用于详情、关于这类以阅读为主的页面。
 */
export function PageShell({
  current,
  children,
  narrow = false,
}: {
  current?: string;
  children: React.ReactNode;
  narrow?: boolean;
}) {
  return (
    <div className="shell">
      <Sidebar current={current} />
      <div className="shell__main">
        <PhoneBar current={current} />
        <main className={narrow ? "main main--narrow" : "main"}>{children}</main>
        <SiteFooter narrow={narrow} />
      </div>
    </div>
  );
}

import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

/**
 * 页面外壳：站头 + 主区 + 站脚。
 *
 * `current` 用于高亮导航，传路由路径（如 `/all/`）。
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
    <>
      <SiteHeader current={current} />
      <main className={narrow ? "wrap wrap-narrow" : "wrap"}>{children}</main>
      <SiteFooter />
    </>
  );
}

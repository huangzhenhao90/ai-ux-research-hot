import Link from "next/link";

/**
 * 详情页最上面的返回链接：「← 返回用研社招 · 阿里巴巴的全部岗位」。
 *
 * 放在页首而不是页尾：读者是从列表点进来的，想回去时不该先拉到最底下。
 * 第一项是「返回」，其余是同一列表里相关的入口。
 */
export function Crumbs({ items }: { items: { href: string; label: string }[] }) {
  return (
    <nav className="crumbs" aria-label="返回">
      {items.map((item, index) => (
        <span key={item.href}>
          {index > 0 ? <span className="crumbs__sep"> · </span> : null}
          <Link href={item.href}>
            {index === 0 ? "← " : ""}
            {item.label}
          </Link>
        </span>
      ))}
    </nav>
  );
}

import Link from "next/link";

import { PageShell } from "@/components/PageShell";

export default function NotFound() {
  return (
    <PageShell>
      <div className="page-head">
        <h1>没有这个页面</h1>
        <p className="page-head__desc">
          链接可能过期了，或者这条内容已经不公开。
        </p>
      </div>
      <p>
        <Link href="/">回到首页</Link> · <Link href="/all/">全部动态</Link> ·{" "}
        <Link href="/search/">搜索</Link>
      </p>
    </PageShell>
  );
}

import { getSite } from "@/lib/data";

/**
 * URhot 标志：青底圆角方块里一个连体的「UR」（User Research），右上角一苗火（hot）。
 *
 * 与 `app/icon.svg`（浏览器标签页图标）是同一个图形，改一处记得改另一处。
 * 底色、火苗色固定，不跟深浅色走：它是品牌色，不是界面色。
 * 这是本站自己设计的标志，与 NOTICE 里提到的上游项目的名称、Logo 无关。
 */
export function LogoMark({ size = 30 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className="logo-mark"
      aria-hidden="true"
      focusable="false"
    >
      <rect width="32" height="32" rx="9" fill="#176b75" />
      <path
        d="M6.2 11.5v8.7a4.8 4.8 0 0 0 9.6 0v-8.7"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M15.8 11.5h3.2a3.4 3.4 0 0 1 0 6.8h-3.2M18.8 18.3l3.4 6.2"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        transform="translate(25.4 12.4) scale(1.05)"
        fill="#f2b84b"
        d="M0-10.5C.9-8 3.7-6.6 3.7-3.4 3.7-1.4 2.1 0 0 0S-3.7-1.4-3.7-3.4c0-1.7.8-2.8 1.7-3.8.1 1.4.7 2.2 1.5 2.4C-.3-7.6-.6-9.2 0-10.5z"
      />
    </svg>
  );
}

/** 标志 + 字标「URhot」：UR 粗、hot 细并用强调色。 */
export function Wordmark({ small = false }: { small?: boolean }) {
  return (
    <span className={small ? "wordmark wordmark--small" : "wordmark"}>
      <LogoMark size={small ? 26 : 32} />
      <span className="wordmark__text">
        <b>UR</b>
        <span>hot</span>
      </span>
    </span>
  );
}

/**
 * 「真知浩见出品」：出品方署名，写成一枚胶囊放在明显位置（侧栏、手机顶栏、关于页）。
 * 文案来自 `config/site.yaml` 的 `byline`。
 *
 * ⚠️ 只能在服务端组件里用（它读 `getSite()`，链着 node:fs）；`LogoMark`、`Wordmark` 没有这个限制。
 */
export function Byline({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const { byline } = getSite();
  if (!byline) return null;
  return <span className={`byline byline--${size}`}>{byline}</span>;
}

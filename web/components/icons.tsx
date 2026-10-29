/**
 * 内联描边图标（不走图标字体，也不发网络请求）。
 *
 * 图标路径改编自上游开源项目的前端（MIT），来源与版权声明见仓库根目录 NOTICE。
 */
import type { ReactNode, SVGProps } from "react";

type P = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 18, children, ...rest }: P & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export type Icon = (p: P) => ReactNode;

export const IconBolt: Icon = (p) => (
  <Svg {...p}>
    <path d="M13 2.5L4.5 13.5H11l-1 8L19.5 10.5H13z" />
  </Svg>
);
export const IconList: Icon = (p) => (
  <Svg {...p}>
    <path d="M8 6h13M8 12h13M8 18h13" />
    <circle cx="3.5" cy="6" r="1" />
    <circle cx="3.5" cy="12" r="1" />
    <circle cx="3.5" cy="18" r="1" />
  </Svg>
);
export const IconGrid: Icon = (p) => (
  <Svg {...p}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
  </Svg>
);
export const IconCap: Icon = (p) => (
  <Svg {...p}>
    <path d="M2.5 9.5L12 5l9.5 4.5L12 14z" />
    <path d="M6.5 11.5v4.2c0 1.3 2.5 2.8 5.5 2.8s5.5-1.5 5.5-2.8v-4.2" />
    <path d="M21.5 9.5v5" />
  </Svg>
);
export const IconBriefcase: Icon = (p) => (
  <Svg {...p}>
    <rect x="3.5" y="7.5" width="17" height="12" rx="2" />
    <path d="M9 7.5V6a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 6v1.5" />
    <path d="M3.5 12.5h17" />
  </Svg>
);
export const IconSearch: Icon = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="M20 20l-4.2-4.2" />
  </Svg>
);
export const IconHeart: Icon = (p) => (
  <Svg {...p}>
    <path d="M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0112 7.3a4.3 4.3 0 017.5 2.5C19.5 15.4 12 20 12 20z" />
  </Svg>
);
export const IconRss: Icon = (p) => (
  <Svg {...p}>
    <path d="M5 11a8 8 0 018 8M5 4.5A14.5 14.5 0 0119.5 19" />
    <circle cx="6" cy="18" r="1.3" />
  </Svg>
);
export const IconSun: Icon = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4L6 18M18 6l1.4-1.4" />
  </Svg>
);
export const IconMoon: Icon = (p) => (
  <Svg {...p}>
    <path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z" />
  </Svg>
);
export const IconMonitor: Icon = (p) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="12" rx="2" />
    <path d="M8 20h8M12 16v4" />
  </Svg>
);
export const IconChevronDown: Icon = (p) => (
  <Svg {...p}>
    <path d="M6 9l6 6 6-6" />
  </Svg>
);
/** 书签：默认描边；收藏后传 `fill="currentColor"` 变实心。 */
export const IconBookmark: Icon = (p) => (
  <Svg {...p}>
    <path d="M6.5 3.5h11a1 1 0 011 1V20.5l-6.5-4.3-6.5 4.3V4.5a1 1 0 011-1z" />
  </Svg>
);
export const IconDownload: Icon = (p) => (
  <Svg {...p}>
    <path d="M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19.5h14" />
  </Svg>
);
export const IconUpload: Icon = (p) => (
  <Svg {...p}>
    <path d="M12 15V4M7.5 8.5L12 4l4.5 4.5M5 19.5h14" />
  </Svg>
);
export const IconExternal: Icon = (p) => (
  <Svg {...p}>
    <path d="M14 4.5h5.5V10M19.5 4.5L11 13M18 14v4.5a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 014 18.5v-11A1.5 1.5 0 015.5 6H10" />
  </Svg>
);

/**
 * 百度统计（站点 PV / UV）。
 *
 * 安装代码放在根布局 `<head>`（`app/layout.tsx`），`output: "export"` 之后每个 HTML 都带这段，
 * 以后新增的页面只要还走根布局就会自动带上。站点 ID 不是密钥，本来就会出现在页面里。
 */
export const BAIDU_SITE_ID = "83c75a4bd0be4caa753d999c2313e715";

/** 百度统计官方安装代码（不含外层 `<script>` 标签）。 */
export const BAIDU_TONGJI_SNIPPET = `var _hmt = _hmt || [];
(function() {
  var hm = document.createElement("script");
  hm.src = "https://hm.baidu.com/hm.js?${BAIDU_SITE_ID}";
  var s = document.getElementsByTagName("script")[0];
  s.parentNode.insertBefore(hm, s);
})();`;

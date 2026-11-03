// node --experimental-strip-types --test e2e/featured.test.mjs
import assert from "node:assert/strict";
import test from "node:test";
import { balanceFeatured } from "../lib/featured.ts";

function select(sources, size = 50) {
  const items = sources.map((sourceName, id) => ({ item: { id, sourceName } }));
  return balanceFeatured([{ day: "2026-11-03", items }], size).flatMap(day => day.items.map(row => row.item.sourceName));
}
const repeat = (source, count) => Array(count).fill(source);

test("50 条中最多 24 条同源，超额时用后续来源补齐", () => {
  const rows = select([...repeat("A", 25), ...repeat("B", 20), ...repeat("C", 10)]);
  assert.equal(rows.length, 54);
  assert.equal(rows.slice(0, 50).filter(x => x === "A").length, 24);
});

test("末页用实际条数校验，合并 arXiv 分类订阅", () => {
  assert.deepEqual(select(["arXiv", "arXiv cs.HC", "B", "C"]), ["arXiv", "B", "C"]);
  assert.deepEqual(select(["A", "A", "B"]), []);
});

test("每次展开和不足一整页的尾部均满足严格上限", () => {
  const rows = select([...repeat("A", 20), ...repeat("B", 21), ...repeat("C", 6), ...repeat("B", 40), ...repeat("C", 10), ...repeat("D", 10)], 10);
  assert.ok(rows.length > 20 && rows.length % 10 !== 0);
  for (let end = 10; end < rows.length + 10; end += 10) {
    const shown = rows.slice(0, end);
    for (const source of new Set(shown)) {
      assert.ok(2 * shown.filter(value => value === source).length < shown.length);
    }
  }
});

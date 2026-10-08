import { splitTabs } from "@/lib/apps";

const items = ["a", "b", "c", "d", "e"].map((id) => ({ id, label: id }));
const widths = { a: 100, b: 100, c: 100, d: 100, e: 100, __more: 80 };

test("shows every tab when they fit", () => {
  // 5 × 100px, the active one set in bold (+8%).
  expect(splitTabs(items, widths, 510, "a").extra).toEqual([]);
  expect(splitTabs(items, widths, 500, "a").extra).not.toEqual([]);
});

test("fills the row before reaching for More", () => {
  const { shown, extra } = splitTabs(items, widths, 400, "a");
  // 400 − 80 for More leaves room for three 100px tabs (the active one is a little wider).
  expect(shown.map((i) => i.id)).toEqual(["a", "b", "c"]);
  expect(extra.map((i) => i.id)).toEqual(["d", "e"]);
});

test("the page you're on keeps its tab in the bar", () => {
  const { shown, extra } = splitTabs(items, widths, 400, "e");
  expect(shown.map((i) => i.id)).toEqual(["a", "b", "e"]);
  expect(extra.map((i) => i.id)).toEqual(["c", "d"]);
});

test("shows everything until widths are measured", () => {
  expect(splitTabs(items, null, 0, "a").shown).toHaveLength(5);
});

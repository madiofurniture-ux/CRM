import { localDateStr } from "./format";

// Regression for the meeting-scheduler timezone offset bug: meetings
// scheduled for "today" were saved/displayed as the next day. Root cause
// was `d.toISOString()` (UTC) applied to a Date built from local calendar
// fields (Meets.jsx's week-grid days and default new-meeting date) — in
// any timezone ahead of UTC (IST is UTC+5:30) that shifts the date
// backward, so a meeting genuinely dated today rendered one grid column
// later. Force IST so this reproduces regardless of the machine running it.
process.env.TZ = "Asia/Kolkata";

test("a meeting scheduled at 19:30 IST keeps that same calendar date", () => {
  const d = new Date(2026, 8, 12, 19, 30); // 19:30 local, 12 Sept 2026
  expect(localDateStr(d)).toBe("2026-09-12");
});

test("local midnight keeps its own date instead of shifting to the previous day", () => {
  // This is the case `toISOString()` got wrong: local midnight IST is
  // 18:30 UTC the day before, so slicing the UTC string returned "09-11".
  const midnight = new Date(2026, 8, 12, 0, 0);
  expect(localDateStr(midnight)).toBe("2026-09-12");
});

// Offline self-check for the read-time best-price join on /picks.
//   node tests/frontend/picks.selfcheck.js
// BEST PRICE and EDGE PTS come from best_lines.json, not from the sealed
// slate — a slate seals weeks before the books post, so those fields freeze
// as nulls and have to be filled at read time. The thing that can silently
// rot is the join: a changed game_id shape or an overwritten sealed value is
// invisible to a build and shows up as a column of dots (or, worse, a wrong
// price on a sealed row). fillBestPrices lives inline in picks.html, so this
// lifts the function out of the page source and runs it against stubs.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SITE = path.join(__dirname, "..", "..", "site", "public");
const page = fs.readFileSync(path.join(SITE, "picks.html"), "utf8");

const fn = page.match(/function fillBestPrices\(s\)\{[\s\S]*?\n\}/);
assert.ok(fn, "fillBestPrices not found in picks.html — did it get renamed?");

// best_lines.json as the pipeline writes it: NFL only, keyed by game_id,
// and covering just the games the books have actually posted.
const BEST = { games: [
  { game_id: "2026_01_TB_CIN", best_price: -190, best_book: "BetMGM",
    n_books: 11, edge_pts: 4.18 },
  { game_id: "2026_01_BAL_IND", best_price: -175, best_book: "Bovada",
    n_books: 9, edge_pts: 3.03 },
]};

function run(games, { ok = true, body = BEST } = {}) {
  const sandbox = {
    Promise, JSON,
    fetch: () => Promise.resolve({ ok, json: () => Promise.resolve(body) }),
  };
  vm.createContext(sandbox);
  vm.runInContext(fn[0] + "\n;__out = fillBestPrices(__s);", 
    Object.assign(sandbox, { __s: { games } }), { filename: "picks.html" });
  return sandbox.__out.then(() => games);
}

(async () => {
  // 1. A null row is filled from the matching best_lines entry.
  let g = (await run([{ game_id: "2026_01_TB_CIN", best_price: null,
                        best_book: null, edge_pts: null, n_books: null }]))[0];
  assert.strictEqual(g.best_price, -190, "best_price not filled");
  assert.strictEqual(g.best_book, "BetMGM", "best_book not filled");
  assert.strictEqual(g.edge_pts, 4.18, "edge_pts not filled");
  assert.strictEqual(g.n_books, 11, "n_books not filled");

  // 2. A sealed value always wins — the join fills nulls, it never overwrites.
  g = (await run([{ game_id: "2026_01_TB_CIN", best_price: -205,
                    best_book: "FanDuel", edge_pts: 9.9, n_books: 3 }]))[0];
  assert.strictEqual(g.best_price, -205, "sealed best_price was clobbered");
  assert.strictEqual(g.best_book, "FanDuel", "sealed best_book was clobbered");
  assert.strictEqual(g.edge_pts, 9.9, "sealed edge_pts was clobbered");

  // 3. A game the books have not posted stays honestly null — never invented.
  g = (await run([{ game_id: "2026_01_MIA_LV", best_price: null,
                    best_book: null, edge_pts: null, n_books: null }]))[0];
  assert.strictEqual(g.best_price, null, "invented a price for an unpriced game");
  assert.strictEqual(g.edge_pts, null, "invented an edge for an unpriced game");

  // 4. A missing or broken best_lines.json degrades to the empty state, and
  //    must not reject — an unreachable file is dots, not a dead page.
  g = (await run([{ game_id: "2026_01_TB_CIN", best_price: null }],
                 { ok: false }))[0];
  assert.strictEqual(g.best_price, null, "404 should leave the column empty");
  g = (await run([{ game_id: "2026_01_TB_CIN", best_price: null }],
                 { body: null }))[0];
  assert.strictEqual(g.best_price, null, "null payload should leave it empty");

  console.log("picks selfcheck OK");
})().catch((e) => { console.error(e.message); process.exit(1); });

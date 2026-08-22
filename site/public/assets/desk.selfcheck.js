// Offline self-check for the phone tab bar's you-are-here logic.
//   node site/public/assets/desk.selfcheck.js
// The bar is injected on every non-embedded screen, so the one thing that can
// silently rot is which tab lights up: a wrong or missing aria-current is
// invisible to a build and obvious to a visitor. desk.js is a browser file
// with no module system, so this loads it under the smallest globals it
// touches at load time (location.search, window) and reads tabs() back off
// the window.Desk export.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const src = fs.readFileSync(path.join(__dirname, "desk.js"), "utf8");

function tabsAt(pathname) {
  const sandbox = {
    location: { pathname, search: "", origin: "https://sooth.bet" },
    // no .m-tabs in the document: the page has no bar of its own yet
    document: { querySelector: () => null, addEventListener: () => {} },
    navigator: { userAgent: "selfcheck" },
    addEventListener: () => {},
    setTimeout: () => {}, setInterval: () => {},
    MutationObserver: null,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "desk.js" });
  return sandbox.window.Desk.tabs();
}

// which tab carries aria-current, by its label
function lit(html) {
  return (html.match(/<a [^>]*aria-current="page"[^>]*>(?:<[^>]+>)*([A-Z]+)</) || [])[1] || null;
}

// 1. Each tab's own route lights that tab and nothing else.
for (const [route, label] of [["/", "BOARD"], ["/picks", "PICKS"],
                              ["/trust", "LEDGER"], ["/ask", "ANALYST"],
                              ["/alerts", "ALERTS"]]) {
  const html = tabsAt(route);
  assert.strictEqual(lit(html), label, `${route} should light ${label}`);
  assert.strictEqual((html.match(/aria-current/g) || []).length, 1,
    `${route} lit more than one tab`);
}

// 2. A page the shell reaches THROUGH a tab keeps that tab lit. This is the
//    case that was broken: "SEE ALL" off the board landed on /market with
//    every tab dark, so the visitor had no sense of place.
for (const route of ["/market", "/edges", "/game"]) {
  assert.strictEqual(lit(tabsAt(route)), "BOARD", `${route} should light BOARD`);
}

// 3. .html and a trailing slash are the same room as the bare path.
assert.strictEqual(lit(tabsAt("/picks.html")), "PICKS");
assert.strictEqual(lit(tabsAt("/market.html")), "BOARD");
assert.strictEqual(lit(tabsAt("/")), "BOARD");

// 4. Fine-print pages belong to no tab and must light none, rather than
//    guessing and telling the visitor they are somewhere they are not.
for (const route of ["/learn", "/record", "/verify", "/disclaimers"]) {
  assert.strictEqual(lit(tabsAt(route)), null, `${route} should light nothing`);
}

// 5. A page that already has a bar never gets a second one stacked on it.
{
  const sandbox = {
    location: { pathname: "/", search: "" },
    document: { querySelector: () => ({}), addEventListener: () => {} },
    navigator: { userAgent: "selfcheck" },
    addEventListener: () => {}, setTimeout: () => {}, setInterval: () => {},
    MutationObserver: null,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(src, sandbox, { filename: "desk.js" });
  assert.strictEqual(sandbox.window.Desk.tabs(), "",
    "a page with its own .m-tabs (index.html) must not get a second bar");
}

// 6. All five surfaces are present and in the shell's order.
{
  const html = tabsAt("/");
  const order = (html.match(/>([A-Z]+)</g) || []).map(s => s.slice(1, -1));
  assert.deepStrictEqual(order, ["BOARD", "PICKS", "LEDGER", "ANALYST", "ALERTS"]);
  assert.ok(/aria-label="Main"/.test(html), "nav needs its landmark label");
}

console.log("desk selfcheck OK");

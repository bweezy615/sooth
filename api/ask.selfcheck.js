// Offline self-check for the Ask AI function — runs without an API key.
//   node api/ask.selfcheck.js
// Fails loudly if the compliance floor or the board-context wiring regresses.
const assert = require("assert");
const ask = require("./ask.js");

// the system prompt must carry every banned word as a prohibition + the 85% cap
const banned = ["guaranteed", "lock", "risk-free", "insider", "sure thing"];
banned.forEach(function (w) {
  assert(ask.SYSTEM.includes(w), "system prompt must name banned word: " + w);
});
assert(ask.SYSTEM.includes("85%"), "system prompt must state the 85% cap");
assert(/NO betting advice/i.test(ask.SYSTEM), "system prompt must disclaim advice");

// buildPrompt must fold the live numbers in and echo the question
const board = { boards: [{ sport: "mlb", events: [{ home: "DET", away: "CLE" }] }] };
const props = { props: [{ player: "Skubal", best_price: 105, best_book: "fanduel" }] };
const p = ask.buildPrompt(board, props, "is skubal over 6.5 a good number?");
assert(p.includes("fanduel"), "prompt must include the live best-book context");
assert(p.includes("Skubal"), "prompt must include the live props context");
assert(p.includes("skubal over 6.5"), "prompt must include the visitor question");

// length cap holds
const long = ask.buildPrompt(board, props, "x".repeat(5000));
assert(long.indexOf("x".repeat(ask.MAX_Q + 1)) === -1, "question must be capped at MAX_Q");

// extractUrl finds a pasted link and strips trailing prose punctuation
assert(ask.extractUrl("read this dk https://sportsbook.dk.com/slip/abc123.") ===
  "https://sportsbook.dk.com/slip/abc123", "must extract url without trailing dot");
assert(ask.extractUrl("no link here") === null, "no url ⇒ null");

// a scraped bet slip gets folded into the prompt; without one it's omitted
const withSlip = ask.buildPrompt(board, props, "is this fair?", "Tigers ML -120 @ FanDuel");
assert(withSlip.includes("Tigers ML -120"), "prompt must include the scraped slip");
assert(withSlip.includes("bet-slip link"), "prompt must frame the scraped slip");
assert(ask.buildPrompt(board, props, "is this fair?").indexOf("bet-slip link") === -1,
  "no slip ⇒ no slip framing");

// --- entitlement gate (the Pro perk). The live site can't show this until the
// cap turns on Sept 1, so force capActive=true and drive every branch. ---
process.env.AUTH_SECRET = "test-secret-please-ignore";
const auth = require("./_auth.js");
const DAY = "2026-09-02";
const noCookies = { headers: {} };
const withCookie = (name, val) =>
  ({ headers: { cookie: name + "=" + encodeURIComponent(val) } });

// cap OFF (today, pre-Sept-1): everyone allowed, no counter written
let g = ask.gateAsk(noCookies, false, DAY);
assert(g.allowed === true && g.cookie === null, "cap off ⇒ unlimited, no counter");

// cap ON + valid Pro cookie ⇒ unlimited, and Pro never gets a free-counter cookie
const proTok = auth.sign({ email: "a@b.com", exp: Date.now() + 1e6 });
g = ask.gateAsk(withCookie("sooth_pro", proTok), true, DAY);
assert(g.allowed === true && g.cookie === null, "Pro ⇒ unlimited");

// cap ON + free first read ⇒ allowed and handed a counter cookie
g = ask.gateAsk(noCookies, true, DAY);
assert(g.allowed === true && g.cookie && g.cookie.indexOf("sooth_ask=") === 0,
  "free under limit ⇒ allowed + counter");

// cap ON + free already at the limit ⇒ blocked (this is the 429)
const atLimit = auth.sign({ date: DAY, n: ask.FREE_ASK_LIMIT, exp: Date.now() + 1e6 });
assert(ask.gateAsk(withCookie("sooth_ask", atLimit), true, DAY).allowed === false,
  "free at limit ⇒ blocked");

// yesterday's maxed counter doesn't carry over — a new day resets
const yesterday = auth.sign({ date: "2026-09-01", n: 99, exp: Date.now() + 1e6 });
assert(ask.gateAsk(withCookie("sooth_ask", yesterday), true, DAY).allowed === true,
  "stale day ⇒ counter resets");


// ---- matchup mode -------------------------------------------------------
// The rule that lets an injury panel and a price gap be trusted: the model is
// handed the arithmetic and forbidden from adding to it.
assert(/VERBATIM/.test(ask.SYSTEM), "system prompt must forbid unsourced numbers");
assert(/not to add to it/.test(ask.SYSTEM), "system prompt must state the phrasing-only role");

const research = {
  reports: [{
    event_id: "401872656", home: "Seattle Seahawks", away: "New England Patriots",
    kickoff: "2026-09-10T00:20Z",
    odds: { spread: { shoppable: false, vig_pts: 4.76, books: ["DraftKings"] } },
    facts: [{ kind: "single_book", text: "Only DraftKings posts this game." }],
  }],
};

assert(ask.findReport(research, "401872656"), "must find a report by event id");
assert(ask.findReport(research, 401872656), "event id must match across types");
assert(ask.findReport(research, "nope") === null, "unknown event ⇒ null");
assert(ask.findReport(null, "401872656") === null, "missing research ⇒ null");

const m = ask.buildMatchupPrompt(research.reports[0], "is this worth betting?");
assert(m.includes("Seattle Seahawks"), "matchup prompt must name the teams");
assert(m.includes("single_book"), "matchup prompt must carry the computed facts");
assert(/computed from this data, not written by a model/.test(m),
  "matchup prompt must tell the model the facts are not its own");
assert(/no best price to shop yet/.test(m),
  "matchup prompt must handle the one-book case explicitly");
assert(m.includes("is this worth betting?"), "matchup prompt must echo the question");

const longQ = ask.buildMatchupPrompt(research.reports[0], "y".repeat(5000));
assert(longQ.indexOf("y".repeat(ask.MAX_Q + 1)) === -1,
  "matchup question must be capped at MAX_Q");

console.log("ask.selfcheck: OK");

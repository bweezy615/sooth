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

console.log("ask.selfcheck: OK");

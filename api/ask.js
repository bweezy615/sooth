// Ask AI — read-a-bet. A Vercel Node serverless function (repo-root /api).
//
// The only non-static piece of sooth: it calls Claude with the live board as
// context so a visitor can run a bet past the numbers. The compliance floor
// (PRODUCT.md) is baked into the system prompt AND kept out of the browser —
// the API key never leaves the server.
//
// Zero deps: Node 18+ on Vercel has global fetch.

const MODEL = "claude-haiku-4-5"; // cheapest; bump here if reads need more depth
const MAX_Q = 500; // input length cap — the floor against abuse/runaway cost

// The house voice + the legal floor, in one place. Every read passes through it.
const SYSTEM = [
  "You are the read-a-bet assistant for sooth.bet, an odds analysis tool.",
  "sooth is NOT a sportsbook, does not take wagers, and gives NO betting advice.",
  "You explain the math: the de-vigged fair price, which book has the best number,",
  "and the line-shopping edge in points. Shopping the best price is +EV on its own",
  "arithmetic; a forecast does not have to be right for that to hold.",
  "",
  "Hard rules, never break them:",
  "- Never say a bet will win, is profitable, or is a good pick.",
  "- Never use the words: guaranteed, lock, risk-free, insider, sure thing.",
  "- Never state a confidence above 85%.",
  "- Our own prediction model is measured WORSE than the closing market; never",
  "  present it as an edge. The edge is price, not prediction.",
  "- Be terse. The audience is sharp bettors who know what vig is.",
  "- End with one line: \"Not advice. Prices move; check the book.\"",
].join("\n");

// Pure, testable: fold the live board + the question into the user message.
// Kept separate from the handler so the self-check can exercise it offline.
function buildPrompt(board, props, question) {
  var ctx = { board: board || null, props: props || null };
  return (
    "Live sooth data (best price per side, de-vigged fair line, edge in points):\n" +
    JSON.stringify(ctx).slice(0, 12000) +
    "\n\nThe visitor asks:\n" + String(question).slice(0, MAX_Q) +
    "\n\nAnswer using only the numbers above. If the bet is not in the data, say so" +
    " and explain what to check (fair price vs the book's price, and who has the best number)."
  );
}

async function fetchJSON(base, path) {
  try {
    var r = await fetch(base + path, { headers: { accept: "application/json" } });
    return r.ok ? await r.json() : null;
  } catch (e) { return null; }
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.statusCode = 405; res.setHeader("Allow", "POST");
    return res.end(JSON.stringify({ error: "POST only" }));
  }
  var key = process.env.ANTHROPIC_API_KEY;
  if (!key) {
    res.statusCode = 500;
    return res.end(JSON.stringify({ error: "Ask AI is not configured yet." }));
  }

  // body may arrive parsed (Vercel) or raw; handle both
  var body = req.body;
  if (typeof body === "string") { try { body = JSON.parse(body); } catch (e) { body = {}; } }
  var question = (body && body.question ? String(body.question) : "").trim();
  if (!question) {
    res.statusCode = 400;
    return res.end(JSON.stringify({ error: "Ask a question about a bet." }));
  }
  if (question.length > MAX_Q) question = question.slice(0, MAX_Q);

  var host = req.headers["x-forwarded-host"] || req.headers.host;
  var proto = req.headers["x-forwarded-proto"] || "https";
  var base = host ? proto + "://" + host : "";
  var board = await fetchJSON(base, "/data/board.json");
  var props = await fetchJSON(base, "/data/props.json");

  try {
    var r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 600,
        system: SYSTEM,
        messages: [{ role: "user", content: buildPrompt(board, props, question) }],
      }),
    });
    if (!r.ok) {
      res.statusCode = 502;
      return res.end(JSON.stringify({ error: "The read is unavailable right now." }));
    }
    var data = await r.json();
    var answer = (data.content || []).map(function (b) { return b.text || ""; }).join("").trim();
    res.statusCode = 200;
    res.setHeader("content-type", "application/json");
    return res.end(JSON.stringify({ answer: answer }));
  } catch (e) {
    res.statusCode = 502;
    return res.end(JSON.stringify({ error: "The read is unavailable right now." }));
  }
};

module.exports.buildPrompt = buildPrompt;
module.exports.SYSTEM = SYSTEM;
module.exports.MAX_Q = MAX_Q;

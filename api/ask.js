// Ask AI — read-a-bet. A Vercel Node serverless function (repo-root /api).
//
// The only non-static piece of sooth: it calls Claude with the live board as
// context so a visitor can run a bet past the numbers. The compliance floor
// (PRODUCT.md) is baked into the system prompt AND kept out of the browser —
// the API key never leaves the server.
//
// Zero deps: Node 18+ on Vercel has global fetch.

const auth = require("./_auth.js");
const MODEL = "claude-haiku-4-5"; // cheapest; bump here if reads need more depth
const MAX_Q = 500; // input length cap — the floor against abuse/runaway cost
const FREE_ASK_LIMIT = 3; // free reads/day once the paywall is live (Pro = unlimited)
// Free until Sept 1 2026 — the cap only bites after that (matches the site promise).
const CAP_ACTIVE = Date.now() >= Date.parse("2026-09-01T00:00:00Z");

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

// Pull the first http(s) link out of the question — a pasted bet-slip URL.
// Trailing punctuation from prose ("...at dk.com.") is stripped.
function extractUrl(text) {
  var m = String(text).match(/https?:\/\/[^\s]+/i);
  return m ? m[0].replace(/[)\]}.,;!?]+$/, "") : null;
}

// Pure, testable: fold the live board + the question (+ any scraped bet slip)
// into the user message. Kept separate from the handler so the self-check can
// exercise it offline.
function buildPrompt(board, props, question, betText) {
  var ctx = { board: board || null, props: props || null };
  var slip = betText
    ? "\n\nThe visitor pasted a bet-slip link. Scraped page below — extract the" +
      " wager (team/player, market, line, price, book) from it, then read it" +
      " against the numbers above:\n" + String(betText)
    : "";
  return (
    "Live sooth data (best price per side, de-vigged fair line, edge in points):\n" +
    JSON.stringify(ctx).slice(0, 12000) +
    slip +
    "\n\nThe visitor asks:\n" + String(question).slice(0, MAX_Q) +
    "\n\nAnswer using only the numbers above. If the bet is not in the data, say so" +
    " and explain what to check (fair price vs the book's price, and who has the best number)."
  );
}

// Decide whether this request may run, and what counter cookie to write back.
// Pure over (req, capActive, today) so the self-check can drive every branch
// with no live model call. Returns one of:
//   { allowed:true,  cookie:null }         Pro, or the cap isn't live yet
//   { allowed:true,  cookie:"sooth_ask…" } free user under the daily limit
//   { allowed:false }                      free user out of reads today
function gateAsk(req, capActive, today) {
  if (!capActive || auth.readPro(req)) return { allowed: true, cookie: null };
  var st = auth.verify(auth.parseCookies(req)["sooth_ask"] || "");
  if (!st || st.date !== today) st = { date: today, n: 0 };  // new day resets
  if (st.n >= FREE_ASK_LIMIT) return { allowed: false };
  return {
    allowed: true,
    cookie: auth.cookie("sooth_ask",
      auth.sign({ date: today, n: st.n + 1, exp: Date.now() + 2 * 24 * 3600 * 1000 }),
      2 * 24 * 3600),
  };
}

async function fetchJSON(base, path) {
  try {
    var r = await fetch(base + path, { headers: { accept: "application/json" } });
    return r.ok ? await r.json() : null;
  } catch (e) { return null; }
}

// Firecrawl a pasted bet-slip URL to markdown. Best-effort: any failure returns
// null and the read falls back to the raw question text (URL and all).
async function scrapeBet(url, key) {
  try {
    var r = await fetch("https://api.firecrawl.dev/v2/scrape", {
      method: "POST",
      headers: { "content-type": "application/json", authorization: "Bearer " + key },
      body: JSON.stringify({ url: url, formats: ["markdown"], onlyMainContent: true }),
    });
    if (!r.ok) return null;
    var j = await r.json();
    var md = j && j.data && j.data.markdown ? String(j.data.markdown) : null;
    // ponytail: 4k-char cap on the scraped slip; raise if real slips truncate.
    return md ? md.slice(0, 4000) : null;
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

  // Entitlement + free daily cap. Pro (a valid sooth_pro cookie) is unlimited.
  // Free users get FREE_ASK_LIMIT reads/day; the cap is inactive until Sept 1.
  // The counter cookie is held and only written on a successful answer below, so
  // a read that errors upstream isn't counted against the user.
  var today = new Date().toISOString().slice(0, 10);
  var gate = gateAsk(req, CAP_ACTIVE, today);
  if (!gate.allowed) {
    res.statusCode = 429;
    return res.end(JSON.stringify({
      error: "That's today's free reads used up. Sooth Pro is unlimited — $9.99/mo.",
      upgrade: "/subscribe",
    }));
  }
  var askCookie = gate.cookie;

  var host = req.headers["x-forwarded-host"] || req.headers.host;
  var proto = req.headers["x-forwarded-proto"] || "https";
  var base = host ? proto + "://" + host : "";
  var board = await fetchJSON(base, "/data/board.json");
  var props = await fetchJSON(base, "/data/props.json");

  // If the visitor pasted a bet-slip link and Firecrawl is configured, scrape
  // it and let Claude read the actual wager. Missing key or failed scrape just
  // falls through to reading the raw text.
  var url = extractUrl(question);
  var betText = (url && process.env.FIRECRAWL_API_KEY)
    ? await scrapeBet(url, process.env.FIRECRAWL_API_KEY)
    : null;

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
        messages: [{ role: "user", content: buildPrompt(board, props, question, betText) }],
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
    if (askCookie) res.setHeader("Set-Cookie", askCookie);
    return res.end(JSON.stringify({ answer: answer }));
  } catch (e) {
    res.statusCode = 502;
    return res.end(JSON.stringify({ error: "The read is unavailable right now." }));
  }
};

module.exports.buildPrompt = buildPrompt;
module.exports.extractUrl = extractUrl;
module.exports.gateAsk = gateAsk;
module.exports.SYSTEM = SYSTEM;
module.exports.MAX_Q = MAX_Q;
module.exports.FREE_ASK_LIMIT = FREE_ASK_LIMIT;

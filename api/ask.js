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
// Everything is free for now (user call, 2026-08-21): a working system comes
// before a paywall. The gate machinery below stays tested and ready — re-arm
// by restoring the date check when Pro has something real behind it.
const CAP_ACTIVE = false; // was: Date.now() >= Date.parse("2026-09-01T00:00:00Z")

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
  "- \"POINTS\" ALWAYS MEANS POINTS OF IMPLIED PROBABILITY, never the numeric",
  "  difference between two American prices. TWO FIELDS ALREADY HOLD THESE",
  "  NUMBERS AND YOU MUST QUOTE THEM VERBATIM:",
  "    gain_pts          best price vs worst price on that side",
  "    edge_vs_fair_pts  best price vs the de-vigged fair price",
  "                      (negative = the best number is WORSE than fair)",
  "  Worked example, and this is a real mistake to avoid: a side priced -230",
  "  against a fair price of -212 is NOT \"18 points worse than fair\" — 18 is",
  "  the gap between two American prices, which is meaningless here. That side",
  "  carries edge_vs_fair_pts -1.77, so it is 1.77 points worse than fair.",
  "  If you catch yourself subtracting two prices, stop and read the field.",
  "  If the field is absent, say the figure is not available.",
  "- ABSOLUTE: never state a number that is the arithmetic difference between",
  "  two American prices — not as points, not as a spread, not as variance,",
  "  not in any sentence. Second worked example: best -244 and worst -275 is",
  "  NOT \"31 points\"; that side's spread IS its gain_pts, 2.40. The only",
  "  numbers you may call points are gain_pts, edge_vs_fair_pts, and the",
  "  values inside leaders. Everything else is a price, and prices are quoted,",
  "  never differenced.",
  "- SUPERLATIVES ARE PRECOMPUTED. Any question about the biggest, largest,",
  "  widest or best gap is answered from data.board.leaders — quote the top",
  "  row verbatim, with its game and side. NEVER rank by reading the events",
  "  list yourself; you will get it wrong on a board this size.",
  "- The events list is the COMPLETE board for the sports listed. If a game is",
  "  not in it, that sport or matchup is not currently priced in our capture —",
  "  say exactly that, and never imply the list was cut short.",
  "- EVERY NUMBER YOU STATE MUST APPEAR VERBATIM IN THE JSON YOU WERE GIVEN.",
  "  Do not compute, estimate, average, or recall a statistic. If a number is",
  "  not in the data, say it is not available. The arithmetic was done before",
  "  you were called; your job is to say what it found, not to add to it.",
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
// Book keys are long and repeat on every quote; the whole board only fits the
// context window as abbreviations.
// The board carries book identity in TWO shapes — quotes[].book holds the
// feed key ("draftkings"), best_book holds the display name ("DraftKings") —
// so a key-only map silently produced "DRAF", "MYBO", "BETM" in answers.
var BOOK_ABBR = {draftkings:"DK",fanduel:"FD",betmgm:"MGM",williamhill_us:"CZR",
  betrivers:"BR",bovada:"BOV",betonlineag:"BOL",lowvig:"LVG",betus:"BUS",
  mybookieag:"MYB",fanatics:"FAN",espnbet:"ESPN",caesars:"CZR",mybookie:"MYB",
  betonline:"BOL",williamhill:"CZR",williamhillus:"CZR",betonlineagcom:"BOL"};
function abbr(k){
  if (!k) return "";
  var n = String(k).toLowerCase().replace(/[^a-z]/g, "");
  return BOOK_ABBR[n] || String(k).slice(0, 4).toUpperCase();
}

// A truncated board is worse than a small one: slicing raw JSON at N chars
// drops most games mid-object, and the model then reports a real matchup as
// "not in the data" (measured: 24.9% of the board was reaching it). This
// projects every event into the fields an answer may cite, so the COMPLETE
// board fits with room to spare.
function compactBoard(board) {
  if (!board || !board.boards) return null;
  var events = [];
  board.boards.forEach(function (b) {
    (b.events || []).forEach(function (e) {
      events.push({
        sport: b.sport, game: e.away + " at " + e.home, starts: e.starts,
        n_books: e.n_books,
        sides: (e.sides || []).map(function (s) {
          return {
            side: s.name, best: s.best_price, best_book: abbr(s.best_book),
            worst: s.worst_price, worst_book: abbr(s.worst_book),
            fair: s.fair_price, fair_prob: s.fair_prob,
            gain_pts: s.gain_pts, edge_vs_fair_pts: s.edge_vs_fair_pts,
            books: (s.quotes || []).map(function (q) {
              return abbr(q.book) + " " + (q.price > 0 ? "+" : "") + q.price;
            }).join(","),
          };
        }),
      });
    });
  });
  // A model asked for "the biggest gap" scans 41 events and picks wrong —
  // measured three times, three different answers, none correct. Superlatives
  // are arithmetic, so they get computed here and quoted there, exactly like
  // the research report's facts[]. Same discipline, same reason.
  function rank(field) {
    var rows = [];
    events.forEach(function (e) {
      e.sides.forEach(function (s) {
        if (typeof s[field] === "number")
          rows.push({ game: e.game, sport: e.sport, side: s.side,
                      value: s[field], best: s.best, best_book: s.best_book,
                      worst: s.worst, worst_book: s.worst_book });
      });
    });
    return rows.sort(function (a, b) { return b.value - a.value; }).slice(0, 5);
  }
  return {
    as_of: board.generated_at, market: "moneyline",
    n_events: events.length,
    leaders: {
      note: "PRECOMPUTED. For any 'biggest/largest/widest/best' question, " +
            "quote these rows verbatim. Do not scan the events list to rank.",
      widest_gap_gain_pts: rank("gain_pts"),
      best_vs_fair_edge_pts: rank("edge_vs_fair_pts"),
    },
    events: events,
  };
}

function compactProps(props) {
  if (!props || !props.props) return null;
  return { as_of: props.generated_at, n: props.props.length,
    props: props.props.slice(0, 40).map(function (p) {
      return { player: p.player, market: p.market, line: p.line,
        side: p.side, best: p.best_price, best_book: abbr(p.best_book || ""),
        fair: p.fair_price, gain_pts: p.gain_pts };
    }) };
}

function buildPrompt(board, props, question, betText) {
  var ctx = { board: compactBoard(board), props: compactProps(props) };
  var slip = betText
    ? "\n\nThe visitor pasted a bet-slip link. Scraped page below — extract the" +
      " wager (team/player, market, line, price, book) from it, then read it" +
      " against the numbers above:\n" + String(betText)
    : "";
  return (
    "Live sooth data — the COMPLETE current board (best price per side, " +
    "de-vigged fair line, gain_pts = best-vs-worst in points of implied " +
    "probability, books = every posted price):\n" +
    JSON.stringify(ctx).slice(0, 40000) +
    slip +
    "\n\nThe visitor asks:\n" + String(question).slice(0, MAX_Q) +
    "\n\nAnswer using only the numbers above. If the bet is not in the data, say so" +
    " and explain what to check (fair price vs the book's price, and who has the best number)."
  );
}

// Fold one matchup report into a user message. The report already contains
// every figure the answer may use, including a pre-computed `facts` list built
// in engine/research.py — so this asks for phrasing, not analysis. That split
// is the whole reason the injury panel and the price gap can be trusted: a
// model asked to "analyse the matchup" writes four confident bullets of
// statistics that do not exist.
function buildMatchupPrompt(report, question) {
  return (
    "Matchup report for " + String(report.away) + " at " + String(report.home) +
    " (kickoff " + String(report.kickoff) + "). Everything you may cite is here:\n" +
    JSON.stringify(report).slice(0, 24000) +
    "\n\nThe `facts` array was computed from this data, not written by a model." +
    " Lead with it. `odds.*.shoppable` false means only one book has posted, so" +
    " there is no best price to shop yet and no edge to describe — say that" +
    " plainly rather than reaching for one. `stats.basis_season` is the season" +
    " the form numbers come from; name it if you quote them." +
    "\n\nThe visitor asks:\n" + String(question).slice(0, MAX_Q)
  );
}

// Pull one report out of research.json by event id.
function findReport(research, eventId) {
  var reports = (research && research.reports) || [];
  for (var i = 0; i < reports.length; i++) {
    if (String(reports[i].event_id) === String(eventId)) return reports[i];
  }
  return null;
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
  // Free users get FREE_ASK_LIMIT reads/day when the cap is armed; it is OFF for now.
  // The counter cookie is held and only written on a successful answer below, so
  // a read that errors upstream isn't counted against the user.
  var today = new Date().toISOString().slice(0, 10);
  var gate = gateAsk(req, CAP_ACTIVE, today);
  if (!gate.allowed) {
    res.statusCode = 429;
    return res.end(JSON.stringify({
      error: "That's today's reads used up. There's no paid tier to skip it — " +
             "come back tomorrow, or read the same numbers on the board now.",
    }));
  }
  var askCookie = gate.cookie;

  var host = req.headers["x-forwarded-host"] || req.headers.host;
  var proto = req.headers["x-forwarded-proto"] || "https";
  var base = host ? proto + "://" + host : "";
  var mode = body && body.mode ? String(body.mode) : "board";
  var eventId = body && body.event_id ? String(body.event_id) : "";

  var prompt;
  if (mode === "matchup") {
    var research = await fetchJSON(base, "/data/research.json");
    var report = findReport(research, eventId);
    if (!report) {
      res.statusCode = 404;
      return res.end(JSON.stringify({
        error: "No research report for that game. Reports cover upcoming games only.",
      }));
    }
    prompt = buildMatchupPrompt(report, question);
  } else {
    var board = await fetchJSON(base, "/data/board.json");
    var props = await fetchJSON(base, "/data/props.json");

  // If the visitor pasted a bet-slip link and Firecrawl is configured, scrape
  // it and let Claude read the actual wager. Missing key or failed scrape just
  // falls through to reading the raw text.
    var url = extractUrl(question);
    var betText = (url && process.env.FIRECRAWL_API_KEY)
      ? await scrapeBet(url, process.env.FIRECRAWL_API_KEY)
      : null;
    prompt = buildPrompt(board, props, question, betText);
  }

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
        messages: [{ role: "user", content: prompt }],
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
module.exports.compactBoard = compactBoard;
module.exports.buildMatchupPrompt = buildMatchupPrompt;
module.exports.findReport = findReport;
module.exports.extractUrl = extractUrl;
module.exports.gateAsk = gateAsk;
module.exports.SYSTEM = SYSTEM;
module.exports.MAX_Q = MAX_Q;
module.exports.FREE_ASK_LIMIT = FREE_ASK_LIMIT;

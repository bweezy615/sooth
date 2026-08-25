// Alert subscriptions — signup, double opt-in confirm, preferences, unsubscribe.
//
// A Vercel Node serverless function, zero deps. Three
// jobs behind one path, because they are one resource:
//
//   POST /api/alerts            {email, kinds[], min_pts, teams[]} -> confirm link
//   POST /api/alerts            {token, kinds[], min_pts, teams[]} -> prefs in place
//   GET  /api/alerts?load=T                                 -> current settings
//   GET  /api/alerts?confirm=T                              -> joins the list
//   GET  /api/alerts?unsub=T    (also POST, for one-click)  -> leaves the list
//
// ?load exists because the preferences form OVERWRITES. It posts the whole
// settings object, so a form that opened on defaults would silently wipe a
// watchlist the reader spent real effort building — and they would only find
// out weeks later, by not being emailed. The page reads current settings back
// through this route first and edits from there.
//
// NOTHING IS STORED UNTIL THE CONFIRM LINK IS CLICKED. That is the whole point
// of double opt-in and it doubles as the abuse control on this endpoint: a
// stranger POSTing someone else's address gets a single confirmation email
// sent to the victim, and no record, no list membership, and no further mail
// unless that person themselves clicks. An endpoint that wrote on POST would
// be a subscription-bombing tool.
//
// The list itself lives on Stripe customer metadata (see engine/subscribers.py
// for why). The token scheme is _auth.js, shared with engine/alert_token.py so
// unsubscribe links minted by the Actions sender verify here.
const auth = require("./_auth.js");

const KINDS = ["seal", "graded", "price", "game"];

// The watchlist, mirroring engine/subscribers.py exactly. Sport-scoped because
// bare abbreviations collide across leagues (MIA, PHI, ATL and a dozen more),
// and an unscoped key would mail somebody about the wrong sport's game.
const TEAM_RE = /^[a-z]{2,6}:[A-Z0-9]{2,4}$/;
const TEAMS_MAX_BYTES = 500;   // Stripe's hard cap on one metadata value
const MIN_FLOOR = 1.5, MIN_CEIL = 10.0, MIN_DEFAULT = 2.5;
const CONFIRM_TTL_MS = 48 * 3600 * 1000;
const LINK_TTL_MS = 730 * 24 * 3600 * 1000;
const FROM_ADDR = "Sooth Alerts <alerts@sooth.bet>";
const UA = "sooth-alerts/1.0";

// Metadata keys — must match engine/subscribers.py exactly.
const K_ON = "sooth_alerts", K_KINDS = "sooth_kinds",
      K_MIN = "sooth_min_pts", K_AT = "sooth_confirmed_at",
      K_TEAMS = "sooth_teams", K_SRC = "sooth_source";

const FOOTER =
  "You are receiving this because someone entered this address at sooth.bet/alerts. " +
  "If that wasn't you, ignore this email — nothing is stored and no list was joined " +
  "unless you click the button above. Sooth is an odds analysis tool — not a " +
  "sportsbook, and not betting advice. Prices move — check the book before you bet. " +
  "21+. Problem gambling? Call 1-800-522-4700.";

// ---- validation -------------------------------------------------------------

// Deliberately loose. Strict email regexes reject real addresses (plus-tags,
// new TLDs, unicode locals) and the actual proof of validity is that the
// confirmation link gets clicked, which no regex can approximate.
function validEmail(s) {
  const e = String(s || "").trim();
  return e.length >= 6 && e.length <= 254 && /^[^\s@]+@[^\s@.]+\.[^\s@]+$/.test(e);
}

function cleanKinds(v) {
  const want = Array.isArray(v) ? v : String(v || "").split(",");
  const out = want.map((k) => String(k).trim().toLowerCase())
                  .filter((k) => KINDS.indexOf(k) >= 0);
  return KINDS.filter((k) => out.indexOf(k) >= 0); // stable order, deduped
}

// null means "the caller said nothing about teams, leave the stored list
// alone"; [] means "clear it". The distinction is load-bearing: a stale cached
// copy of the page that predates the watchlist posts no teams field at all,
// and it must not be able to empty somebody's list by omission.
function cleanTeams(v) {
  if (v === undefined || v === null) return null;
  const want = Array.isArray(v) ? v : String(v).split(",");
  const seen = {};
  want.forEach((raw) => {
    const s = String(raw).trim();
    const i = s.indexOf(":");
    if (i < 0) return;
    // Repairing case is safe — it cannot change WHICH team is meant. Anything
    // else malformed is dropped rather than guessed at.
    const k = s.slice(0, i).trim().toLowerCase() + ":" + s.slice(i + 1).trim().toUpperCase();
    if (TEAM_RE.test(k)) seen[k] = 1;
  });
  // Sorted before truncation so the same watchlist always stores the same 60
  // teams rather than a different arbitrary subset on each write.
  const out = [];
  let used = 0;
  Object.keys(seen).sort().forEach((k) => {
    const add = k.length + (out.length ? 1 : 0);
    if (used + add > TEAMS_MAX_BYTES) return;
    out.push(k);
    used += add;
  });
  return out;
}

function clampMin(v) {
  const f = parseFloat(v);
  if (!isFinite(f)) return MIN_DEFAULT;
  return Math.max(MIN_FLOOR, Math.min(MIN_CEIL, f));
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

async function readJson(req) {
  if (req.body && typeof req.body === "object") return req.body;
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf8");
  if (!raw) return {};
  try { return JSON.parse(raw); } catch (e) { return {}; }
}

// ---- Stripe (the list) ------------------------------------------------------

async function stripe(path, key, form) {
  const opts = {
    headers: { authorization: "Bearer " + key, "user-agent": UA },
  };
  if (form) {
    opts.method = "POST";
    opts.headers["content-type"] = "application/x-www-form-urlencoded";
    opts.body = form.toString();
  }
  const r = await fetch("https://api.stripe.com/v1/" + path, opts);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error((j.error && j.error.message) || ("stripe " + r.status));
  return j;
}

// Prefer a record that already carries alert metadata, then any record for the
// address. A person who bought Pro and later subscribes to alerts should end
// up with ONE customer holding both facts, not two records with half the story.
async function findCustomer(email, key) {
  const q = new URLSearchParams({ email: email, limit: "100" });
  const list = await stripe("customers?" + q.toString(), key);
  const rows = list.data || [];
  return rows.find((c) => c.metadata && c.metadata[K_ON] !== undefined) ||
         rows[0] || null;
}

async function upsert(email, kinds, minPts, teams, key) {
  const form = new URLSearchParams();
  form.set("metadata[" + K_ON + "]", "1");
  form.set("metadata[" + K_KINDS + "]", kinds.join(","));
  form.set("metadata[" + K_MIN + "]", String(minPts));
  if (teams) form.set("metadata[" + K_TEAMS + "]", teams.join(","));
  form.set("metadata[" + K_AT + "]", new Date().toISOString());
  form.set("metadata[" + K_SRC + "]", "alerts-page");
  const existing = await findCustomer(email, key);
  if (existing) return stripe("customers/" + existing.id, key, form);
  form.set("email", email);
  return stripe("customers", key, form);
}

// Unsubscribe flips the flag; it never deletes the record. Deleting would let
// the same address be re-added later with no trace that they had once said no,
// and "we lost your opt-out" is the one mistake a mailing list cannot make.
async function optOut(email, key) {
  const existing = await findCustomer(email, key);
  if (!existing) return null;
  const form = new URLSearchParams();
  form.set("metadata[" + K_ON + "]", "0");
  form.set("metadata[sooth_unsub_at]", new Date().toISOString());
  return stripe("customers/" + existing.id, key, form);
}

// Current settings for an address the token already proved. Returns defaults
// rather than 404 for someone who has no record: the honest answer to "what am
// I signed up for" when the answer is nothing.
async function current(email, key) {
  const cust = await findCustomer(email, key);
  const meta = (cust && cust.metadata) || {};
  return {
    email: email,
    kinds: cleanKinds(meta[K_KINDS]),
    min_pts: clampMin(meta[K_MIN]),
    teams: cleanTeams(meta[K_TEAMS]) || [],
    subscribed: String(meta[K_ON] || "") === "1",
  };
}

// ---- the confirmation email -------------------------------------------------

function kindLabel(k) {
  return { seal: "Slate sealed", graded: "Week graded",
           price: "Price divergence", game: "A game you follow" }[k] || k;
}

function qualifier(k, minPts, teams) {
  if (k === "price") return "at " + minPts.toFixed(1) + "+ points";
  // Count, not the roster. Sixty "nba:NYK" strings in a confirmation email is
  // a wall of jargon, and the reader already knows who they picked.
  if (k === "game") {
    const n = (teams || []).length;
    return n ? n + " team" + (n === 1 ? "" : "s") + " on your watchlist" : "";
  }
  return "";
}

function confirmEmail(link, kinds, minPts, teams) {
  const rows = kinds.map((k) => {
    const q = qualifier(k, minPts, teams);
    return '<tr><td style="padding:7px 0;color:#E8EAED;font:14px/1.5 ui-sans-serif,system-ui">' +
      "&middot; " + esc(kindLabel(k)) +
      (q ? ' <span style="color:#8A919D">' + esc(q) + "</span>" : "") +
      "</td></tr>";
  }).join("");

  const html =
    '<div style="max-width:560px;margin:0 auto;background:#0A0B0D;' +
    'border:1px solid rgba(255,255,255,.13);padding:30px 26px">' +
    '<div style="color:#2DD4A7;font:700 12px/1 ui-monospace,monospace;' +
    'letter-spacing:.14em;text-transform:uppercase">Sooth &middot; confirm alerts</div>' +
    '<div style="color:#E8EAED;font:600 18px/1.4 ui-sans-serif,system-ui;' +
    'margin:14px 0 6px">One click and you are on the list.</div>' +
    '<div style="color:#B4BAC4;font:14px/1.6 ui-sans-serif,system-ui">' +
    "You asked for:</div>" +
    '<table style="width:100%;border-collapse:collapse;margin:6px 0 4px">' +
    rows + "</table>" +
    '<a href="' + esc(link) + '" style="display:inline-block;margin-top:18px;' +
    'background:#2DD4A7;color:#0A0B0D;font:600 14px/1 ui-sans-serif,system-ui;' +
    'text-decoration:none;padding:12px 20px">Confirm this address &rarr;</a>' +
    '<div style="color:#5A6170;font:12px/1.6 ui-sans-serif,system-ui;' +
    'margin-top:14px">This link expires in 48 hours.</div>' +
    '<div style="color:#5A6170;font:11px/1.6 ui-sans-serif,system-ui;' +
    'margin-top:20px;border-top:1px solid rgba(255,255,255,.07);padding-top:14px">' +
    esc(FOOTER) + "</div></div>";

  const text =
    "One click and you are on the list.\n\nYou asked for:\n" +
    kinds.map((k) => {
      const q = qualifier(k, minPts, teams);
      return "  - " + kindLabel(k) + (q ? " " + q : "");
    }).join("\n") +
    "\n\nConfirm this address:\n" + link +
    "\n\nThis link expires in 48 hours.\n\n" + FOOTER + "\n\nsooth.bet";

  return { subject: "Confirm your Sooth alerts", html: html, text: text };
}

async function sendConfirm(to, mail, resendKey) {
  const r = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: "Bearer " + resendKey,
      "content-type": "application/json",
      "user-agent": UA,
    },
    body: JSON.stringify({
      from: FROM_ADDR, to: [to], subject: mail.subject,
      html: mail.html, text: mail.text,
    }),
  });
  if (!r.ok) throw new Error("resend " + r.status);
  return true;
}

// ---- handler ----------------------------------------------------------------

function json(res, code, body) {
  res.statusCode = code;
  res.setHeader("content-type", "application/json");
  res.setHeader("cache-control", "no-store");
  return res.end(JSON.stringify(body));
}
function bounce(res, q) {
  res.statusCode = 302;
  res.setHeader("cache-control", "no-store");
  res.setHeader("Location", "/alerts" + q);
  return res.end();
}

module.exports = async function handler(req, res) {
  const url = new URL(req.url, "https://sooth.bet");
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  const proto = req.headers["x-forwarded-proto"] || "https";
  const base = host ? proto + "://" + host : "https://sooth.bet";
  const stripeKey = process.env.STRIPE_SECRET_KEY || "";
  const resendKey = process.env.RESEND_API_KEY || "";

  // --- leave the list. GET (link click) and POST (RFC 8058 one-click) both. ---
  const unsub = url.searchParams.get("unsub");
  if (unsub) {
    const p = auth.verify(unsub);
    if (!p || p.t !== "u" || !p.e) {
      return req.method === "POST" ? json(res, 400, { error: "bad token" })
                                   : bounce(res, "?state=badlink");
    }
    try {
      if (stripeKey) await optOut(p.e, stripeKey);
    } catch (e) {
      // An unsubscribe must never look like it failed. Log and confirm: the
      // sender re-reads the list every run, so a transient Stripe error here
      // costs one more email, not a permanent opt-out failure.
      console.error("optOut failed", e && e.message);
    }
    return req.method === "POST" ? json(res, 200, { ok: true })
                                 : bounce(res, "?state=off");
  }

  // --- read current settings, so the prefs form edits instead of overwrites ---
  const load = url.searchParams.get("load");
  if (load) {
    const p = auth.verify(load);
    if (!p || (p.t !== "p" && p.t !== "c") || !p.e) {
      return json(res, 400, { error: "expired" });
    }
    if (!stripeKey) return json(res, 500, { error: "not configured" });
    try {
      return json(res, 200, await current(p.e, stripeKey));
    } catch (e) {
      console.error("load failed", e && e.message);
      return json(res, 502, { error: "unavailable" });
    }
  }

  // --- join the list: the confirm link from the double opt-in email ---
  const confirm = url.searchParams.get("confirm");
  if (confirm) {
    const p = auth.verify(confirm);
    if (!p || p.t !== "c" || !p.e) return bounce(res, "?state=badlink");
    if (!stripeKey) return bounce(res, "?state=error");
    try {
      await upsert(p.e, cleanKinds(p.k), clampMin(p.m), cleanTeams(p.w), stripeKey);
    } catch (e) {
      console.error("upsert failed", e && e.message);
      return bounce(res, "?state=error");
    }
    return bounce(res, "?state=on");
  }

  if (req.method !== "POST") {
    res.statusCode = 405;
    res.setHeader("Allow", "GET, POST");
    return json(res, 405, { error: "POST to subscribe" });
  }

  const body = await readJson(req);
  const kinds = cleanKinds(body.kinds);
  const minPts = clampMin(body.min_pts);
  const teams = cleanTeams(body.teams);
  if (!kinds.length) {
    return json(res, 400, { error: "Pick at least one thing to be told about." });
  }
  // Game alerts with an empty watchlist match no game and would send nothing
  // at all. Silently accepting that is worse than refusing it: the reader
  // waits for emails that were never going to arrive.
  if (kinds.indexOf("game") >= 0 && (!teams || !teams.length)) {
    return json(res, 400, {
      error: "Pick at least one team to follow, or turn off game reminders.",
    });
  }

  // --- change prefs in place. The token already proves this address. ---
  if (body.token) {
    const p = auth.verify(body.token);
    if (!p || (p.t !== "p" && p.t !== "c") || !p.e) {
      return json(res, 400, { error: "That preferences link has expired. Sign up again to reset it." });
    }
    if (!stripeKey) return json(res, 500, { error: "Alerts are not configured yet." });
    try {
      await upsert(p.e, kinds, minPts, teams, stripeKey);
    } catch (e) {
      console.error("prefs upsert failed", e && e.message);
      return json(res, 500, { error: "Could not save that. Try again in a minute." });
    }
    return json(res, 200, { ok: true, saved: true, email: p.e });
  }

  // --- new signup: mail a confirm link, store nothing ---
  const email = String(body.email || "").trim();
  if (!validEmail(email)) {
    return json(res, 400, { error: "That doesn't look like an email address." });
  }
  if (!resendKey || !process.env.AUTH_SECRET) {
    return json(res, 500, { error: "Alerts are not configured yet." });
  }
  // The watchlist rides in the token rather than in a pending record: still
  // NOTHING IS STORED until the link is clicked, which is what stops this
  // endpoint being a subscription-bombing tool. 500 bytes of teams is ~700
  // base64 characters, comfortably inside any URL limit.
  const token = auth.sign({
    t: "c", e: email, k: kinds.join(","), m: minPts,
    w: (teams || []).join(","),
    exp: Date.now() + CONFIRM_TTL_MS,
  });
  const link = base + "/api/alerts?confirm=" + encodeURIComponent(token);
  try {
    await sendConfirm(email, confirmEmail(link, kinds, minPts, teams), resendKey);
  } catch (e) {
    console.error("confirm send failed", e && e.message);
    return json(res, 502, { error: "We couldn't send the confirmation email. Try again in a minute." });
  }
  return json(res, 200, { ok: true, sent: true });
};

// Exported for api/alerts.selfcheck.js — the pure parts, checkable with no
// network and no keys.
module.exports._internals = {
  validEmail, cleanKinds, clampMin, cleanTeams, confirmEmail, kindLabel,
  qualifier, KINDS, MIN_FLOOR, MIN_CEIL, MIN_DEFAULT, LINK_TTL_MS,
  TEAM_RE, TEAMS_MAX_BYTES,
};

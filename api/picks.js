// The pick engine's only content gate (docs/pick-engine-plan.md, Step 2).
//
// Pro cookie          -> the full sealed slate (data/pro/latest.pro.json)
// no cookie, pre-kick -> 200 with a locked teaser: game count, seal metadata,
//                        the top-divergence matchup BY NAME ONLY. Never a
//                        naked 401 — the teaser is the funnel.
// after first kickoff -> the full payload for EVERYONE. Time decay is both
//                        the honesty mechanism and the free archive: the
//                        paywall sells timing, it never touches the proof.
//
// Fails closed: no AUTH_SECRET means nobody is Pro (auth.readPro returns
// null); a missing pro payload file returns 404 with a plain reason.
const fs = require("fs");
const path = require("path");
const auth = require("./_auth.js");

const PRO_FILE = path.join(process.cwd(), "data/pro/latest.pro.json");

function loadSlate(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) {
    return null;
  }
}

function firstKickoff(slate) {
  // earliest_kickoff is sealed into the commitment; trust the slate file.
  const t = Date.parse(slate.earliest_kickoff || "");
  return Number.isNaN(t) ? null : t;
}

function teaser(slate) {
  // Divergence order is baked into the pro file at write time (weekly.py
  // sorts by it), so the top matchup is just the first row — names only.
  const top = (slate.games && slate.games[0]) || null;
  return {
    locked: true,
    slate_id: slate.slate_id,
    game_count: (slate.games || []).length,
    sealed_at: slate.committed_at,
    merkle_root: slate.merkle_root,
    unlocks_at: slate.earliest_kickoff,
    top_divergence_matchup: top ? top.away + " at " + top.home : null,
    upgrade: "/subscribe",
    note: "The full slate is sealed and Pro-only until first kickoff, then " +
          "free to everyone. Pro buys timing, not wins - our model's " +
          "published record is at /record.",
  };
}

function respond(res, code, body) {
  res.statusCode = code;
  res.setHeader("content-type", "application/json");
  res.setHeader("cache-control", "no-store"); // entitlement-shaped, never cache
  return res.end(JSON.stringify(body));
}

function handler(req, res, opts) {
  const o = opts || {};
  const file = o.file || PRO_FILE;
  const now = o.now || Date.now();

  const slate = loadSlate(file);
  if (!slate) {
    return respond(res, 404, {
      error: "No sealed slate is published yet. Slates seal Wednesdays in season.",
    });
  }

  const kick = firstKickoff(slate);
  const open = kick !== null && now >= kick; // time decay: post-kick == public
  if (open || auth.readPro(req)) {
    return respond(res, 200, Object.assign({ locked: false }, slate));
  }
  return respond(res, 200, teaser(slate));
}

module.exports = handler;
module.exports.teaser = teaser;
module.exports.PRO_FILE = PRO_FILE;

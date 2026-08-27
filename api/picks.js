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
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const auth = require("./_auth.js");

const PRO_FILE = path.join(process.cwd(), "data/pro/latest.pro.enc");
const META_FILE = path.join(process.cwd(), "data/pro/latest.meta.json");

// The ledger repo is public by design, so the pro payload sits in it as
// AES-256-GCM ciphertext: base64(nonce(12) || ct || tag(16)). The key lives
// only in this function's env. No key, wrong key, tampered blob -> null,
// and the caller degrades to the teaser: fail closed, never fail open.
function decryptSlate(file, keyHex) {
  try {
    if (!/^[0-9a-f]{64}$/i.test(keyHex || "")) return null;
    const raw = Buffer.from(fs.readFileSync(file, "utf8").trim(), "base64");
    const nonce = raw.subarray(0, 12);
    const tag = raw.subarray(raw.length - 16);
    const ct = raw.subarray(12, raw.length - 16);
    const d = crypto.createDecipheriv(
      "aes-256-gcm", Buffer.from(keyHex, "hex"), nonce);
    d.setAuthTag(tag);
    return JSON.parse(Buffer.concat([d.update(ct), d.final()]).toString("utf8"));
  } catch (e) {
    return null;
  }
}

function loadMeta(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) {
    return null;
  }
}

function firstKickoff(meta) {
  // earliest_kickoff is sealed into the commitment; trust the sidecar.
  const t = Date.parse(meta.earliest_kickoff || "");
  return Number.isNaN(t) ? null : t;
}

function teaser(meta) {
  // Everything here comes from the plaintext sidecar weekly.py writes —
  // teaser fields only, never an opinion.
  return {
    locked: true,
    slate_id: meta.slate_id,
    game_count: meta.game_count,
    sealed_at: meta.sealed_at,
    merkle_root: meta.merkle_root,
    unlocks_at: meta.earliest_kickoff,
    top_divergence_matchup: meta.top_divergence_matchup || null,
    // How many games cleared the engine's edge bar — a count, never a side.
    // Zero is a real and publishable answer, so `null` means the sidecar
    // predates the field rather than "no plays"; the two must not collapse.
    qualified_plays:
      typeof meta.qualified_plays === "number" ? meta.qualified_plays : null,
    // No `upgrade` field any more: the checkout was removed on 2026-08-22 and
    // there is nothing to sell. The lock is the proof mechanism, not a price.
    // This note now renders ONLY when the slate cannot be decrypted — there
    // is no lock left to describe. Say what is actually true in that state.
    note: "The sealed commitment above is published and verifiable at " +
          "/verify. Our model's published record is at /record.",
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
  const metaFile = o.metaFile || META_FILE;
  const now = o.now || Date.now();
  const keyHex = "keyHex" in o ? o.keyHex : process.env.PRO_PAYLOAD_KEY;

  const meta = loadMeta(metaFile);
  if (!meta) {
    return respond(res, 404, {
      error: "No sealed slate is published yet. Slates seal Wednesdays in season.",
    });
  }

  // THE SLATE IS OPEN. There is no time gate any more (removed 2026-08-22).
  //
  // The gate sold TIMING for the paid tier: Pro saw the slate at seal time,
  // everyone else waited for first kickoff. The paid tier is gone, so the lock
  // had nothing left to sell.
  //
  // It was never what made the commitment trustworthy, and the site said
  // otherwise for a while, so: commit-reveal integrity rests on the hash being
  // published and externally timestamped BEFORE the event, not on when the
  // contents are shown. 2026-W01's root was anchored to a public GitHub commit
  // five weeks before its first kickoff. Revealing early proves exactly as
  // much. {slate_id}.reveal.json has in fact carried every prediction in the
  // clear the whole time.
  //
  // Still fails CLOSED on a decryption problem: a slate we cannot read is
  // reported as unavailable, never invented.
  const slate = decryptSlate(file, keyHex);
  if (slate) {
    return respond(res, 200, Object.assign({ locked: false }, slate));
  }
  const t = teaser(meta);
  t.note = "The full payload is temporarily unavailable - the sealed " +
           "commitment above still stands. " + t.note;
  return respond(res, 200, t);
}

module.exports = handler;
module.exports.teaser = teaser;
module.exports.PRO_FILE = PRO_FILE;
module.exports.META_FILE = META_FILE;
module.exports.decryptSlate = decryptSlate;

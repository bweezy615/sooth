// Offline self-check for the pick-engine gate — runs with no server and no
// AUTH_SECRET requirement beyond what each case sets.
//   node api/picks.selfcheck.js
// Drives every branch: missing file, the open slate before AND after kickoff,
// and every fail-CLOSED path (no key, wrong key, tampered blob).
//
// The time gate was removed on 2026-08-22 with the paid tier, so the cases
// that used to assert "locked before kickoff" now assert the opposite: the
// slate is served whenever it can be decrypted. What must NOT change is that
// an unreadable slate degrades to the teaser rather than to an invention.
const assert = require("assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

process.env.AUTH_SECRET = "selfcheck-secret";
const picks = require("./picks.js");
const auth = require("./_auth.js");

function fakeRes() {
  const r = { headers: {}, body: null, statusCode: 0 };
  r.setHeader = (k, v) => { r.headers[k.toLowerCase()] = v; };
  r.end = (b) => { r.body = JSON.parse(b); };
  return r;
}
function req(cookie) { return { headers: cookie ? { cookie } : {} }; }

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "picks-"));
const file = path.join(tmp, "latest.pro.enc");
const metaFile = path.join(tmp, "latest.meta.json");
const future = new Date(Date.now() + 48 * 3600 * 1000).toISOString();
const past = new Date(Date.now() - 3600 * 1000).toISOString();
const KEY = "11".repeat(32);           // 64 hex chars, test-only

function encrypt(obj, keyHex) {
  const crypto = require("crypto");
  const nonce = crypto.randomBytes(12);
  const c = crypto.createCipheriv("aes-256-gcm", Buffer.from(keyHex, "hex"), nonce);
  const ct = Buffer.concat([c.update(JSON.stringify(obj), "utf8"), c.final()]);
  return Buffer.concat([nonce, ct, c.getAuthTag()]).toString("base64");
}
function slate(kick) {
  return {
    slate_id: "2099-W01-nfl", merkle_root: "ab".repeat(32),
    committed_at: new Date().toISOString(), earliest_kickoff: kick,
    games: [
      { game_id: "g2", home: "DET", away: "NO", divergence: 0.21,
        independent: { pick: "NO", prob: 0.55 } },
      { game_id: "g1", home: "SEA", away: "NE", divergence: 0.02,
        independent: { pick: "SEA", prob: 0.64 } },
    ],
  };
}
function writeBoth(kick) {
  const s = slate(kick);
  fs.writeFileSync(file, encrypt(s, KEY));
  fs.writeFileSync(metaFile, JSON.stringify({
    slate_id: s.slate_id, game_count: s.games.length,
    sealed_at: s.committed_at, merkle_root: s.merkle_root,
    earliest_kickoff: s.earliest_kickoff,
    top_divergence_matchup: "NO at DET",
  }));
}

// 1. missing meta -> 404 with a reason, never a crash
let res = fakeRes();
picks(req(), res, { metaFile: path.join(tmp, "nope.json"), keyHex: KEY });
assert.equal(res.statusCode, 404);
assert(/No sealed slate/.test(res.body.error), "missing file must explain itself");

// 2. sealed, BEFORE first kickoff, anonymous -> the full slate
// This is the case that inverted. The commitment is what proves the picks
// predate the games; showing them early proves exactly as much.
writeBoth(future);
res = fakeRes();
picks(req(), res, { file, metaFile, keyHex: KEY });
assert.equal(res.statusCode, 200, "must be 200, never 401");
assert.equal(res.body.locked, false, "no time gate: the slate is open");
assert.equal(res.body.games[0].independent.pick, "NO",
  "the picks are visible before kickoff");
assert.equal(res.body.upgrade, undefined, "nothing to buy");
assert(!/subscribe|\$9/.test(JSON.stringify(res.body)),
  "the payload must not sell anything");
assert.equal(res.headers["cache-control"], "no-store");

// 3. a comped cookie changes nothing — everyone gets the same payload
const cookie = "sooth_pro=" +
  auth.sign({ email: "t@x.com", exp: Date.now() + 60000 });
res = fakeRes();
picks(req(cookie), res, { file, metaFile, keyHex: KEY });
assert.equal(res.body.locked, false);
assert.equal(res.body.games[0].independent.pick, "NO");

// 4. after first kickoff -> unchanged, still the full slate
writeBoth(past);
res = fakeRes();
picks(req(), res, { file, metaFile, keyHex: KEY });
assert.equal(res.body.locked, false, "post-kick the payload is public");

// 5. NO KEY -> teaser with the truth, never a 500, never an invented slate
res = fakeRes();
picks(req(), res, { file, metaFile, keyHex: "" });
assert.equal(res.statusCode, 200);
assert.equal(res.body.locked, true, "undecryptable must fail closed");
assert(/temporarily unavailable/.test(res.body.note), "and say so");

// 6. wrong key / tampered blob -> same closed teaser
res = fakeRes();
picks(req(), res, { file, metaFile, keyHex: "22".repeat(32) });
assert.equal(res.body.locked, true, "wrong key must fail closed");

// 7. the ciphertext itself must not leak a pick to a repo reader.
// This used to assert the blob did not contain the substring "NO". The blob is
// base64 over a RANDOM nonce, so a given two-character sequence appears by
// chance in a few hundred characters roughly one run in eleven — the check
// failed intermittently for a reason that had nothing to do with encryption.
// Test the actual property instead: the committed file must not be readable
// as the payload, and must not carry a distinctive plaintext marker.
const blob = fs.readFileSync(file, "utf8");
assert.throws(() => JSON.parse(blob), "the committed blob must not be plain JSON");
assert(!/"pick"|"independent"|"merkle_root"/.test(blob),
  "plaintext payload keys visible in the committed blob");

// 8. no AUTH_SECRET is no longer relevant to the slate — it gates nothing
// here now — but the endpoint must still serve rather than break.
delete require.cache[require.resolve("./_auth.js")];
delete require.cache[require.resolve("./picks.js")];
process.env.AUTH_SECRET = "";
const picks2 = require("./picks.js");
writeBoth(future);
res = fakeRes();
picks2(req(), res, { file, metaFile, keyHex: KEY });
assert.equal(res.body.locked, false, "the slate does not depend on AUTH_SECRET");

console.log("picks.selfcheck: OK");

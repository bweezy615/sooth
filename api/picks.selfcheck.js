// Offline self-check for the pick-engine gate — runs with no server and no
// AUTH_SECRET requirement beyond what each case sets.
//   node api/picks.selfcheck.js
// Drives every branch: missing file, locked teaser, pro cookie, time decay,
// and the fail-closed path when AUTH_SECRET is absent.
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
const file = path.join(tmp, "latest.pro.json");
const future = new Date(Date.now() + 48 * 3600 * 1000).toISOString();
const past = new Date(Date.now() - 3600 * 1000).toISOString();

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

// 1. missing file -> 404 with a reason, never a crash
let res = fakeRes();
picks(req(), res, { file: path.join(tmp, "nope.json") });
assert.equal(res.statusCode, 404);
assert(/No sealed slate/.test(res.body.error), "missing file must explain itself");

// 2. sealed + pre-kick + anonymous -> 200 locked teaser, names only, no picks
fs.writeFileSync(file, JSON.stringify(slate(future)));
res = fakeRes();
picks(req(), res, { file });
assert.equal(res.statusCode, 200, "teaser must be 200, never 401");
assert.equal(res.body.locked, true);
assert.equal(res.body.game_count, 2);
assert.equal(res.body.top_divergence_matchup, "NO at DET", "names only, from row 0");
assert.equal(res.body.upgrade, "/subscribe");
assert(!JSON.stringify(res.body).includes('"pick"'), "teaser must not leak a pick");
assert.equal(res.headers["cache-control"], "no-store");

// 3. valid pro cookie -> full slate
const cookie = "sooth_pro=" +
  auth.sign({ email: "t@x.com", exp: Date.now() + 60000 });
res = fakeRes();
picks(req(cookie), res, { file });
assert.equal(res.body.locked, false);
assert.equal(res.body.games[0].independent.pick, "NO", "pro sees the picks");

// 4. after first kickoff -> full slate for everyone (time decay)
fs.writeFileSync(file, JSON.stringify(slate(past)));
res = fakeRes();
picks(req(), res, { file });
assert.equal(res.body.locked, false, "post-kick the payload is public");

// 5. fail closed: no AUTH_SECRET means the cookie verifies to nothing
delete require.cache[require.resolve("./_auth.js")];
delete require.cache[require.resolve("./picks.js")];
process.env.AUTH_SECRET = "";
const picks2 = require("./picks.js");
fs.writeFileSync(file, JSON.stringify(slate(future)));
res = fakeRes();
picks2(req(cookie), res, { file });
assert.equal(res.body.locked, true, "no AUTH_SECRET -> nobody is Pro");

console.log("picks.selfcheck: OK");

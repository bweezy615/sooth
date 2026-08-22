// Read-only entitlement probe: does this browser hold a valid sooth_pro cookie?
//
// No secrets, no writes, no Stripe call: it just verifies the signed sooth_pro
// cookie (fails closed to pro:false without AUTH_SECRET or a valid cookie).
//
// Since the paid tier was removed on 2026-08-22 nothing mints that cookie, so
// this answers {"pro":false} for every visitor. Kept because api/picks.js
// still honours a comped cookie and this is the only way to read one back.
const auth = require("./_auth.js");

module.exports = function handler(req, res) {
  const pro = auth.readPro(req);
  res.statusCode = 200;
  res.setHeader("content-type", "application/json");
  res.setHeader("cache-control", "no-store"); // entitlement must never cache
  return res.end(JSON.stringify({
    pro: !!pro,
    email: pro ? (pro.email || null) : null,
  }));
};

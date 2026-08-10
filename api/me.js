// Read-only entitlement probe: does this browser hold a valid Sooth Pro cookie?
//
// It's how the site shows Pro state, and how we confirm a checkout actually
// granted access — hit it after subscribing and it flips to {"pro":true}. No
// secrets, no writes, no Stripe call: it just verifies the signed sooth_pro
// cookie (fails closed to pro:false without AUTH_SECRET or a valid cookie).
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

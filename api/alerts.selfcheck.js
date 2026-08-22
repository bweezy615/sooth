// Offline self-check for the alert subscription endpoint.
//   node api/alerts.selfcheck.js
//
// Drives every branch with no network and no real keys: validation, the
// double-opt-in promise (a POST must not write), confirm, prefs, one-click
// unsubscribe, tampered and expired tokens, and the fail-closed paths when
// AUTH_SECRET / STRIPE_SECRET_KEY / RESEND_API_KEY are missing.
//
// fetch is stubbed and every call is recorded, so "nothing was stored" is
// asserted against the actual absence of a Stripe write rather than assumed.
const assert = require("assert");

process.env.AUTH_SECRET = "selfcheck-secret";
process.env.STRIPE_SECRET_KEY = "sk_test_selfcheck";
process.env.RESEND_API_KEY = "re_selfcheck";

const alerts = require("./alerts.js");
const auth = require("./_auth.js");
const V = alerts._internals;

// ---- harness ----------------------------------------------------------------

let calls = [];
let customers = [];            // what findCustomer will "find"

global.fetch = async function (url, opts) {
  calls.push({ url: String(url), method: (opts && opts.method) || "GET",
               body: opts && opts.body });
  if (String(url).indexOf("api.stripe.com") >= 0) {
    if (String(url).indexOf("customers?") >= 0) {
      return { ok: true, json: async () => ({ data: customers }) };
    }
    return { ok: true, json: async () => ({ id: "cus_new", object: "customer" }) };
  }
  if (String(url).indexOf("api.resend.com") >= 0) {
    return { ok: true, json: async () => ({ id: "email_1" }) };
  }
  throw new Error("unexpected fetch to " + url);
};

function res() {
  const r = { headers: {}, statusCode: 0, body: null, ended: false };
  r.setHeader = (k, v) => { r.headers[k.toLowerCase()] = v; };
  r.end = (b) => { r.ended = true; try { r.body = b ? JSON.parse(b) : null; } catch (e) { r.body = b; } };
  return r;
}
function req(method, path, body) {
  const o = { method: method, url: path, headers: { host: "sooth.bet" }, body: body };
  return o;
}
async function call(method, path, body) {
  calls = [];
  const r = res();
  await alerts(req(method, path, body), r);
  return r;
}
const stripeWrites = () => calls.filter((c) =>
  c.url.indexOf("api.stripe.com") >= 0 && c.method === "POST");
const mails = () => calls.filter((c) => c.url.indexOf("api.resend.com") >= 0);

(async function main() {

  // ---- pure validation ------------------------------------------------------

  assert.ok(V.validEmail("a@b.co"));
  assert.ok(V.validEmail("first.last+tag@sub.example.museum"));
  assert.ok(!V.validEmail("nope"), "no @");
  assert.ok(!V.validEmail("a@b"), "no dot in domain");
  assert.ok(!V.validEmail("a b@c.com"), "space");
  assert.ok(!V.validEmail(""), "empty");
  assert.ok(!V.validEmail("x@" + "y".repeat(300) + ".com"), "over 254");

  // kinds: unknown dropped, deduped, stable order regardless of input order
  assert.deepStrictEqual(V.cleanKinds(["price", "seal"]), ["seal", "price"]);
  assert.deepStrictEqual(V.cleanKinds(["SEAL", "seal", "junk"]), ["seal"]);
  assert.deepStrictEqual(V.cleanKinds("graded,price"), ["graded", "price"]);
  assert.deepStrictEqual(V.cleanKinds([]), []);
  assert.deepStrictEqual(V.cleanKinds(["nope"]), []);

  // threshold clamps rather than trusts
  assert.strictEqual(V.clampMin("2.5"), 2.5);
  assert.strictEqual(V.clampMin(0), V.MIN_FLOOR, "below floor clamps up");
  assert.strictEqual(V.clampMin(999), V.MIN_CEIL, "above ceiling clamps down");
  assert.strictEqual(V.clampMin("abc"), V.MIN_DEFAULT);
  assert.strictEqual(V.clampMin(undefined), V.MIN_DEFAULT);
  assert.strictEqual(V.clampMin(NaN), V.MIN_DEFAULT);

  // the confirmation email carries the compliance floor and escapes the link
  const mail = V.confirmEmail("https://sooth.bet/api/alerts?confirm=a&b=1",
                              ["seal", "price"], 2.5);
  assert.ok(mail.text.indexOf("1-800-522-4700") >= 0, "text footer");
  assert.ok(mail.html.indexOf("1-800-522-4700") >= 0, "html footer");
  assert.ok(mail.text.indexOf("not betting advice") >= 0, "not-advice in text");
  assert.ok(mail.html.indexOf("&amp;b=1") >= 0, "link is html-escaped");
  assert.ok(mail.text.indexOf("2.5+ points") >= 0, "threshold stated back");
  assert.ok(mail.text.indexOf("48 hours") >= 0, "expiry stated");
  // The anti-bombing sentence is a promise to a stranger; it must ship.
  assert.ok(mail.text.indexOf("nothing is stored") >= 0, "no-store promise");

  // ---- POST signup: mails a link, writes NOTHING ----------------------------

  let r = await call("POST", "/api/alerts",
                     { email: "new@x.com", kinds: ["seal", "price"], min_pts: 3 });
  assert.strictEqual(r.statusCode, 200, JSON.stringify(r.body));
  assert.deepStrictEqual(r.body, { ok: true, sent: true });
  assert.strictEqual(mails().length, 1, "one confirmation email");
  assert.strictEqual(stripeWrites().length, 0,
    "DOUBLE OPT-IN: a POST must not create or modify any customer");

  // the emailed token round-trips and carries exactly what was asked for
  const sentBody = JSON.parse(mails()[0].body);
  const link = /confirm=([^"&\s]+)/.exec(sentBody.text)[1];
  const payload = auth.verify(decodeURIComponent(link));
  assert.strictEqual(payload.t, "c");
  assert.strictEqual(payload.e, "new@x.com");
  assert.strictEqual(payload.k, "seal,price");
  assert.strictEqual(payload.m, 3);
  assert.ok(payload.exp > Date.now() && payload.exp < Date.now() + 49 * 3600e3,
    "confirm token expires in ~48h");

  // ---- POST validation failures --------------------------------------------

  r = await call("POST", "/api/alerts", { email: "bad", kinds: ["seal"] });
  assert.strictEqual(r.statusCode, 400);
  assert.ok(/email address/.test(r.body.error));
  assert.strictEqual(mails().length, 0, "invalid address is never mailed");

  r = await call("POST", "/api/alerts", { email: "a@b.co", kinds: [] });
  assert.strictEqual(r.statusCode, 400);
  assert.ok(/at least one/.test(r.body.error));

  r = await call("POST", "/api/alerts", { email: "a@b.co", kinds: ["junk"] });
  assert.strictEqual(r.statusCode, 400, "unknown kinds subscribe to nothing");

  // ---- GET confirm: joins the list -----------------------------------------

  const good = auth.sign({ t: "c", e: "new@x.com", k: "seal,price", m: 3,
                           exp: Date.now() + 3600e3 });
  customers = [];
  r = await call("GET", "/api/alerts?confirm=" + encodeURIComponent(good));
  assert.strictEqual(r.statusCode, 302);
  assert.strictEqual(r.headers.location, "/alerts?state=on");
  assert.strictEqual(r.headers["cache-control"], "no-store");
  let w = stripeWrites();
  assert.strictEqual(w.length, 1, "exactly one customer write");
  assert.ok(w[0].url.endsWith("/customers"), "no existing record -> create");
  assert.ok(w[0].body.indexOf("email=new%40x.com") >= 0, "creates with the address");
  assert.ok(w[0].body.indexOf("sooth_alerts%5D=1") >= 0, "opt-in flag set");
  assert.ok(w[0].body.indexOf("sooth_kinds%5D=seal%2Cprice") >= 0, "kinds stored");
  assert.ok(w[0].body.indexOf("sooth_min_pts%5D=3") >= 0, "threshold stored");
  assert.ok(w[0].body.indexOf("sooth_confirmed_at") >= 0, "consent is timestamped");

  // an existing record is UPDATED, never duplicated
  customers = [{ id: "cus_pro", email: "new@x.com", metadata: {} }];
  r = await call("GET", "/api/alerts?confirm=" + encodeURIComponent(good));
  w = stripeWrites();
  assert.strictEqual(w.length, 1);
  assert.ok(w[0].url.endsWith("/customers/cus_pro"),
    "an existing Stripe customer gains alert metadata rather than a twin record");
  assert.ok(w[0].body.indexOf("email=") < 0, "update does not rewrite the address");

  // a record already carrying alert metadata wins over a bare one
  customers = [{ id: "cus_bare", email: "new@x.com", metadata: {} },
               { id: "cus_alerts", email: "new@x.com", metadata: { sooth_alerts: "0" } }];
  await call("GET", "/api/alerts?confirm=" + encodeURIComponent(good));
  assert.ok(stripeWrites()[0].url.endsWith("/customers/cus_alerts"),
    "the alert record is preferred, so re-subscribing clears the old opt-out");

  // ---- bad confirm tokens ---------------------------------------------------

  for (const [label, tok] of [
    ["tampered", good.slice(0, -3) + "aaa"],
    ["garbage", "not-a-token"],
    ["expired", auth.sign({ t: "c", e: "a@b.co", k: "seal", m: 2, exp: Date.now() - 1 })],
    ["wrong type", auth.sign({ t: "u", e: "a@b.co", exp: Date.now() + 3600e3 })],
    ["no email", auth.sign({ t: "c", k: "seal", m: 2, exp: Date.now() + 3600e3 })],
  ]) {
    r = await call("GET", "/api/alerts?confirm=" + encodeURIComponent(tok));
    assert.strictEqual(r.headers.location, "/alerts?state=badlink", label);
    assert.strictEqual(stripeWrites().length, 0, label + " must not write");
  }

  // ---- prefs in place -------------------------------------------------------

  const pref = auth.sign({ t: "p", e: "old@x.com", exp: Date.now() + 3600e3 });
  customers = [{ id: "cus_x", email: "old@x.com", metadata: { sooth_alerts: "1" } }];
  r = await call("POST", "/api/alerts",
                 { token: pref, kinds: ["graded"], min_pts: 5 });
  assert.strictEqual(r.statusCode, 200, JSON.stringify(r.body));
  assert.deepStrictEqual(r.body, { ok: true, saved: true, email: "old@x.com" });
  assert.strictEqual(mails().length, 0, "changing prefs does not re-confirm");
  w = stripeWrites();
  assert.ok(w[0].body.indexOf("sooth_kinds%5D=graded") >= 0);
  assert.ok(w[0].body.indexOf("sooth_min_pts%5D=5") >= 0);

  // a prefs token cannot be used for a different address than it names
  r = await call("POST", "/api/alerts",
                 { token: pref, email: "attacker@x.com", kinds: ["seal"] });
  assert.strictEqual(stripeWrites()[0].url, "https://api.stripe.com/v1/customers/cus_x",
    "the token's address wins; a body address cannot redirect the write");

  r = await call("POST", "/api/alerts", { token: "junk", kinds: ["seal"] });
  assert.strictEqual(r.statusCode, 400);
  assert.ok(/expired/.test(r.body.error), "expired prefs link explains itself");

  // ---- unsubscribe ----------------------------------------------------------

  const ut = auth.sign({ t: "u", e: "old@x.com", exp: Date.now() + LINK_YEARS() });
  customers = [{ id: "cus_x", email: "old@x.com", metadata: { sooth_alerts: "1" } }];

  r = await call("GET", "/api/alerts?unsub=" + encodeURIComponent(ut));
  assert.strictEqual(r.headers.location, "/alerts?state=off");
  w = stripeWrites();
  assert.ok(w[0].body.indexOf("sooth_alerts%5D=0") >= 0, "flag cleared");
  assert.ok(w[0].body.indexOf("sooth_unsub_at") >= 0, "opt-out is timestamped");
  assert.ok(w[0].url.indexOf("cus_x") >= 0 && w[0].method === "POST");
  assert.ok(!/customers\/cus_x\?/.test(w[0].url), "update, not delete");

  // RFC 8058 one-click: the same token over POST answers JSON, not a redirect
  r = await call("POST", "/api/alerts?unsub=" + encodeURIComponent(ut));
  assert.strictEqual(r.statusCode, 200);
  assert.deepStrictEqual(r.body, { ok: true });

  // an unsubscribe must never look like it failed, even if Stripe is down
  const realFetch = global.fetch;
  global.fetch = async function (url, opts) {
    if (String(url).indexOf("api.stripe.com") >= 0) throw new Error("stripe down");
    return realFetch(url, opts);
  };
  r = await call("GET", "/api/alerts?unsub=" + encodeURIComponent(ut));
  assert.strictEqual(r.headers.location, "/alerts?state=off",
    "a Stripe outage still confirms the unsubscribe to the human");
  global.fetch = realFetch;

  // an unsubscribe token that is not ours is refused, not silently honoured
  r = await call("GET", "/api/alerts?unsub=" + encodeURIComponent(ut.slice(0, -2) + "zz"));
  assert.strictEqual(r.headers.location, "/alerts?state=badlink");

  // ---- method + fail-closed -------------------------------------------------

  r = await call("GET", "/api/alerts");
  assert.strictEqual(r.statusCode, 405);
  assert.strictEqual(r.headers.allow, "GET, POST");

  const savedResend = process.env.RESEND_API_KEY;
  process.env.RESEND_API_KEY = "";
  r = await call("POST", "/api/alerts", { email: "a@b.co", kinds: ["seal"] });
  assert.strictEqual(r.statusCode, 500);
  assert.ok(/not configured/.test(r.body.error));
  assert.strictEqual(mails().length, 0);
  process.env.RESEND_API_KEY = savedResend;

  const savedAuth = process.env.AUTH_SECRET;
  process.env.AUTH_SECRET = "";
  r = await call("POST", "/api/alerts", { email: "a@b.co", kinds: ["seal"] });
  assert.strictEqual(r.statusCode, 500, "no signing secret => no signup");
  // and with no secret, a previously valid confirm link stops working
  r = await call("GET", "/api/alerts?confirm=" + encodeURIComponent(good));
  assert.strictEqual(r.headers.location, "/alerts?state=badlink",
    "fails CLOSED: without AUTH_SECRET no token verifies, so nobody is added");
  assert.strictEqual(stripeWrites().length, 0);
  process.env.AUTH_SECRET = savedAuth;

  const savedStripe = process.env.STRIPE_SECRET_KEY;
  process.env.STRIPE_SECRET_KEY = "";
  r = await call("GET", "/api/alerts?confirm=" + encodeURIComponent(good));
  assert.strictEqual(r.headers.location, "/alerts?state=error",
    "no list to write to is an error, not a silent success");
  process.env.STRIPE_SECRET_KEY = savedStripe;

  console.log("alerts.selfcheck: OK");
})().catch((e) => { console.error(e); process.exit(1); });

function LINK_YEARS() { return 730 * 24 * 3600 * 1000; }

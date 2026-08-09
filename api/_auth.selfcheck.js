// Offline self-check for the auth helpers.  node api/_auth.selfcheck.js
const assert = require("assert");
process.env.AUTH_SECRET = "test-secret-please-ignore";
const auth = require("./_auth.js");

// round-trip: a signed payload verifies back to itself
const tok = auth.sign({ email: "a@b.com", exp: Date.now() + 60000 });
const p = auth.verify(tok);
assert(p && p.email === "a@b.com", "signed payload must verify back");

// tampering the body breaks the signature
const bad = "eyJldmlsIjp0cnVlfQ." + tok.slice(tok.lastIndexOf(".") + 1);
assert(auth.verify(bad) === null, "tampered body must fail verification");

// expiry is enforced
assert(auth.verify(auth.sign({ email: "x", exp: Date.now() - 1 })) === null,
  "expired token must fail");

// fails CLOSED with no secret
process.env.AUTH_SECRET = "";
assert(auth.verify(tok) === null, "no AUTH_SECRET ⇒ verify must return null (no Pro)");
process.env.AUTH_SECRET = "test-secret-please-ignore";

// cookie parsing + readPro
const req = { headers: { cookie: "foo=1; sooth_pro=" + encodeURIComponent(tok) + "; bar=2" } };
assert(auth.parseCookies(req).foo === "1", "must parse multiple cookies");
assert(auth.readPro(req).email === "a@b.com", "readPro must pull the sooth_pro cookie");
assert(auth.readPro({ headers: {} }) === null, "no cookie ⇒ not Pro");

// cookie() sets the security flags
const c = auth.cookie("sooth_pro", "v", 3600);
["HttpOnly", "Secure", "SameSite=Lax", "Path=/", "Max-Age=3600"].forEach(function (f) {
  assert(c.includes(f), "cookie must set " + f);
});

console.log("_auth.selfcheck: OK");

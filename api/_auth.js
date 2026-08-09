// Shared auth helpers for Sooth Pro. Zero deps (Node's built-in crypto). The
// leading underscore keeps Vercel from turning this into an HTTP endpoint.
//
// A token is  base64url(JSON payload) + "." + HMAC-SHA256(body, AUTH_SECRET).
// Stateless: no DB. Entitlement is a signed cookie set only after Stripe
// confirms payment (see session-verify.js). Fails CLOSED — with no AUTH_SECRET,
// verify() always returns null, so Pro is never granted by accident.
const crypto = require("crypto");

function secret() { return process.env.AUTH_SECRET || ""; }

function b64url(buf) {
  return Buffer.from(buf).toString("base64")
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function fromB64url(s) {
  return Buffer.from(String(s).replace(/-/g, "+").replace(/_/g, "/"), "base64");
}
function hmac(body) {
  return b64url(crypto.createHmac("sha256", secret()).update(body).digest());
}

// sign(payload) -> "body.sig". payload.exp (ms epoch) is enforced by verify().
function sign(payload) {
  const body = b64url(JSON.stringify(payload));
  return body + "." + hmac(body);
}

// verify(token) -> payload | null. Rejects a missing secret, tampering, or expiry.
function verify(token) {
  if (!token || !secret()) return null;
  const dot = String(token).lastIndexOf(".");
  if (dot < 0) return null;
  const body = token.slice(0, dot), sig = token.slice(dot + 1);
  const a = Buffer.from(sig), b = Buffer.from(hmac(body));
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
  let p;
  try { p = JSON.parse(fromB64url(body).toString("utf8")); } catch (e) { return null; }
  if (p && p.exp && Date.now() > p.exp) return null;
  return p;
}

function parseCookies(req) {
  const out = {}; const h = req.headers && req.headers.cookie; if (!h) return out;
  String(h).split(";").forEach(function (kv) {
    const i = kv.indexOf("="); if (i < 0) return;
    out[kv.slice(0, i).trim()] = decodeURIComponent(kv.slice(i + 1).trim());
  });
  return out;
}
function cookie(name, value, maxAgeSec) {
  return name + "=" + encodeURIComponent(value) +
    "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=" + maxAgeSec;
}

// readPro(req) -> the sooth_pro entitlement payload, or null if not Pro.
function readPro(req) { return verify(parseCookies(req)["sooth_pro"] || ""); }

module.exports = { sign, verify, parseCookies, cookie, readPro };

// Embedded Stripe Checkout — the POS for Sooth Pro, on sooth.bet (no redirect).
//
// Sibling of ask.js: a Vercel Node serverless function, zero deps (Node 18+ has
// global fetch). It creates an *embedded* Checkout Session for the $9.99/mo
// subscription and hands the browser back only the session's client_secret. The
// Stripe SECRET key never leaves the server — it lives in the STRIPE_SECRET_KEY
// env var on the pick-engine Vercel project, exactly like ANTHROPIC_API_KEY.
//
// The card fields render inside Stripe's secure iframe mounted on our page, so
// the customer never leaves sooth.bet and we never touch raw card data (PCI).

// The $9.99/mo price. Not secret (it's a public identifier), env-overridable so
// a price change is a Vercel setting, not a code deploy.
const PRICE = process.env.STRIPE_PRICE_ID || "price_1U2dGcAUGlXR5yMgu8YJLXLy";

// Pure + testable: the form body for a POST to /v1/checkout/sessions. Kept out
// of the handler so the self-check can assert the params without a live key.
// return_url must keep the literal {CHECKOUT_SESSION_ID} — Stripe fills it in.
function buildSessionForm(priceId, returnUrl) {
  const p = new URLSearchParams();
  p.set("ui_mode", "embedded_page"); // Stripe renamed the old "embedded" value
  p.set("mode", "subscription");
  p.set("line_items[0][price]", priceId);
  p.set("line_items[0][quantity]", "1");
  p.set("return_url", returnUrl);
  return p.toString();
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    res.statusCode = 405; res.setHeader("Allow", "POST");
    return res.end(JSON.stringify({ error: "POST only" }));
  }
  const key = process.env.STRIPE_SECRET_KEY;
  if (!key) {
    res.statusCode = 500;
    return res.end(JSON.stringify({ error: "Checkout is not configured yet." }));
  }

  const host = req.headers["x-forwarded-host"] || req.headers.host;
  const proto = req.headers["x-forwarded-proto"] || "https";
  const base = host ? proto + "://" + host : "https://sooth.bet";
  // Return through session-verify: it confirms payment with Stripe, grants the
  // sooth_pro cookie, then redirects to the /subscribe-complete thank-you page.
  const returnUrl = base + "/api/session-verify?session_id={CHECKOUT_SESSION_ID}";

  try {
    const r = await fetch("https://api.stripe.com/v1/checkout/sessions", {
      method: "POST",
      headers: {
        authorization: "Bearer " + key,
        "content-type": "application/x-www-form-urlencoded",
      },
      body: buildSessionForm(PRICE, returnUrl),
    });
    const data = await r.json();
    if (!r.ok || !data.client_secret) {
      // surface Stripe's message server-side only; keep the client generic
      console.error("stripe checkout session failed:", data && data.error);
      res.statusCode = 502;
      return res.end(JSON.stringify({ error: "Could not start checkout. Try again." }));
    }
    res.statusCode = 200;
    res.setHeader("content-type", "application/json");
    return res.end(JSON.stringify({ clientSecret: data.client_secret }));
  } catch (e) {
    res.statusCode = 502;
    return res.end(JSON.stringify({ error: "Could not start checkout. Try again." }));
  }
};

module.exports.buildSessionForm = buildSessionForm;
module.exports.PRICE = PRICE;

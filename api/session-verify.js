// Checkout return endpoint. Stripe's embedded checkout redirects the buyer here
// after a subscription. We verify the session server-side with Stripe, grant Pro
// via a signed cookie, then redirect to the on-domain thank-you page.
//
// No DB — the cookie IS the grant (Phase 2 re-checks Stripe for cancellations).
// Fails closed: a bad/unpaid session or missing AUTH_SECRET ⇒ no cookie.
const auth = require("./_auth.js");
const PRO_DAYS = 60;

module.exports = async function handler(req, res) {
  const url = new URL(req.url, "https://sooth.bet");
  const id = url.searchParams.get("session_id") || "";
  const key = process.env.STRIPE_SECRET_KEY;

  function bounce(q) {
    res.statusCode = 302;
    res.setHeader("Location", "/subscribe-complete" + q);
    return res.end();
  }
  if (!id || !key) return bounce("?status=error");

  try {
    const r = await fetch(
      "https://api.stripe.com/v1/checkout/sessions/" + encodeURIComponent(id),
      { headers: { authorization: "Bearer " + key } }
    );
    const s = await r.json();
    const paid = r.ok && (s.status === "complete" || s.payment_status === "paid");
    if (!paid) return bounce("?status=pending");

    const email = (s.customer_details && s.customer_details.email) || "";
    const token = auth.sign({
      email: email,
      customer: s.customer || null,
      exp: Date.now() + PRO_DAYS * 24 * 3600 * 1000,
    });
    res.setHeader("Set-Cookie", auth.cookie("sooth_pro", token, PRO_DAYS * 24 * 3600));
    return bounce("");
  } catch (e) {
    return bounce("?status=error");
  }
};

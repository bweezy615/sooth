// Offline self-check for the checkout function — runs without a Stripe key.
//   node api/checkout.selfcheck.js
// Fails loudly if the session params or the return_url template regress.
const assert = require("assert");
const co = require("./checkout.js");

const ret = "https://sooth.bet/subscribe-complete?session_id={CHECKOUT_SESSION_ID}";
const form = co.buildSessionForm("price_TEST123", ret);
const q = new URLSearchParams(form);

assert(q.get("ui_mode") === "embedded", "must request embedded ui_mode (no redirect)");
assert(q.get("mode") === "subscription", "must be a subscription, not one-off");
assert(q.get("line_items[0][price]") === "price_TEST123", "must carry the price id");
assert(q.get("line_items[0][quantity]") === "1", "quantity must be 1");
// the decoded return_url must still hold Stripe's literal placeholder
assert(q.get("return_url") === ret, "return_url must survive encoding intact");
assert(/\{CHECKOUT_SESSION_ID\}/.test(q.get("return_url")),
  "return_url must keep the {CHECKOUT_SESSION_ID} template for Stripe to fill");
assert(/^price_/.test(co.PRICE), "PRICE must be a Stripe price id");

console.log("checkout.selfcheck: OK");

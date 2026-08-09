# Sooth Pro — Phase 1 (entitlement + gated Ask AI)

## Goal
Turn the live Stripe subscription into a real "Pro" grant, and make **unlimited
Ask AI** the first Pro perk. No database, no new external service.

## Approach (DB-free)
- **Entitlement = a signed cookie** (`sooth_pro`), granted only after Stripe
  confirms a *paid* checkout session. HMAC-SHA256 over the payload with
  `AUTH_SECRET` (Node `crypto`, zero deps). **Fails closed**: no `AUTH_SECRET`
  ⇒ no Pro is ever granted.
- **Stripe is the source of truth** for payment; the cookie is the session.
  Phase 2 re-checks Stripe live (to honor cancellations) and adds magic-link
  cross-device login.

## Pieces
1. `api/_auth.js` — sign/verify tokens, cookie read/write, `readPro(req)`. (+ self-check)
2. `api/session-verify.js` — the checkout `return_url` target: verify the session
   with Stripe → set `sooth_pro` cookie → 302 to `/subscribe-complete`.
3. `api/checkout.js` — point `return_url` at `/api/session-verify`.
4. `api/ask.js` — Pro ⇒ unlimited; free ⇒ 3 reads/day (signed cookie counter).
   The cap only activates **on/after Sept 1** (keeps the free-until-Sept-1
   promise). Failed reads (upstream errors) don't count against the free cap.

## Env
- `AUTH_SECRET` — NEW, add to Vercel pick-engine (Production + Preview). Strong random.
- `STRIPE_SECRET_KEY` — already set.

## Verify
- `node api/_auth.selfcheck.js` (sign/verify/tamper/expiry).
- Live: `session-verify` rejects a bad `session_id`; Ask AI still answers.
- End-to-end Pro: subscribe via `/subscribe?buy=1` (real card) → cookie set → AI unlimited.

## Deferred
- **Phase 1b — alerts:** needs an email sender (Resend + sooth.bet DNS verify).
- **Phase 2:** magic-link login (cross-device), live Stripe re-check on each
  gated request, full Edges suite gating + data exports/API key.

# Sooth Discord — setup

Everything the bot needs is built. What is left is the part that requires a
Discord account: creating the server and the webhooks. That is yours to do —
a webhook URL is a credential and should go straight into GitHub secrets
without passing through a chat window.

Estimated time: about ten minutes.

---

## 1. Create the server

Discord → **+** in the server rail → **Create My Own** → **For a club or
community** → name it **Sooth**.

Server settings worth changing immediately:

| Setting | Value | Why |
|---|---|---|
| Safety Setup → Verification Level | **Medium** | Must have a verified email and be registered 5+ minutes. Stops drive-by spam without annoying real members. |
| Safety Setup → Explicit media filter | **Scan from all members** | |
| Moderation → 2FA requirement for moderation | **On** | |
| Overview → Default notifications | **Only @mentions** | A price feed that pings every member every two hours empties a server fast. |

Set the server description to something that carries the product's actual
claim rather than a growth promise:

> Odds analysis. We publish the best available price and the de-vigged fair
> line. No picks, no tips, no wagers taken. 21+ where lawful.

---

## 2. Channels

Fewer channels than feels natural. An empty channel reads as a dead server,
and this community has one thing to say per board refresh.

```
INFORMATION
  #start-here      read-only. Pinned: what this is, how to read a price.
  #the-rules       read-only. Pinned: compliance post below.

THE BOARD
  #best-prices     read-only. The bot posts here. This is the product.
  #line-moves      read-only. Reserved — nothing posts here yet.

COMMUNITY
  #general         members can post.
  #questions       members can post. Where "what does de-vigged mean" goes.
```

For every read-only channel: **Edit Channel → Permissions → @everyone → Send
Messages: off**, View Channel: on.

Reserve `#line-moves` but do not create it until something posts to it. A
channel that has been empty since launch is worse than one that does not
exist.

---

## 3. Webhooks

Two, because the bot already supports a free and a paid tier and you will not
want to retrofit that later.

`#best-prices` → **Edit Channel → Integrations → Webhooks → New Webhook**

- Name: `Sooth`
- Copy the URL. **Do not paste it into a chat window or a file in this repo.**

Repeat in whatever channel the paid tier will use. If the paid tier does not
exist yet, make the second webhook point at `#best-prices` too and change it
when it does.

---

## 4. Store them as GitHub secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `SOOTH_DISCORD_WEBHOOK_FREE` | the `#best-prices` webhook URL |
| `SOOTH_DISCORD_WEBHOOK_PRO` | the paid-tier webhook URL |

These names are what `engine/alert_discord.py` already reads. Nothing else in
the repo has to change to match them.

---

## 5. Merge the bot

PR #5, branch `feat/discord-community`. It carries `engine/alert_discord.py`
and `.github/workflows/discord.yml`.

Before merging, one decision that is not the bot's to make:

**The best-prices post does not consult `POSTABLE` and will post as soon as the
secrets exist.** No key needs adding to make the channel work. It ranks every
priced side on `edge_vs_fair_pts` and publishes the top few — price arithmetic,
no model involved, nothing gated.

**`POSTABLE` gates a different path entirely** — `--mode edges`, which ranks by
model edge. It is deliberately empty because the strikeout model measured no
edge on the population books actually post (see `/props-model`), and that mode
is now diagnostic-only and cannot publish under any flag. PRODUCT.md carries
"never rank or select anything by model edge" as a hard constraint.

So: if the channel is quiet after setup, the cause is the secrets, the schedule,
or an empty board — never `POSTABLE`. Adding a key there will not make a post
appear, and whoever adds one is claiming someone measured that market. Do not
add one to make the channel look alive.

---

## 6. Test before anyone is in the server

```bash
python -m engine.alert_discord --dry-run
```

Prints the exact post to the terminal and sends nothing. Check three things:

1. It says **best prices**, never picks or plays. PRODUCT.md forbids that
   vocabulary and it is load-bearing, not stylistic.
2. On a normal board every line is *below* consensus fair, and the post says
   so up front rather than leaving a reader to infer it from a minus sign.
3. The footer carries the disclaimer.

Then post once to the live webhook with nobody in the server but you, and
look at it in Discord rather than in a terminal. Embeds render differently
than they read.

---

## 7. Pinned posts

Paste these as-is. Both are written to the audience rule in PRODUCT.md:
a newcomer can follow them, and nothing in them slows down someone who
already knows.

### `#start-here`

> **What this is**
>
> Every major sportsbook prices the same bet slightly differently. Sooth reads
> them all and publishes two numbers: the **best available price** right now,
> and the **fair price** — what the odds would be if the books took no cut.
>
> **Why that is worth something**
>
> Taking −190 instead of −235 on the same bet pays more. That is arithmetic,
> not a prediction. Nothing has to be forecast correctly for a better number
> to be worth more, which is why this is the whole product.
>
> **What we do not do**
>
> We do not sell picks and we do not tell you who wins. We built a prediction
> model, measured it honestly, and published the result: it does not beat the
> market. <https://sooth.bet/props-model>
>
> **Reading a post in #best-prices**
>
> Each line shows the best price, which book has it, and how that price
> compares to the fair line. Most of the time it will be *below* fair — that
> gap is the house's cut and it is on almost every price you will ever see.
> The number worth having is the smallest one.
>
> Full explainer: <https://sooth.bet/learn> · The board: <https://sooth.bet>

### `#the-rules`

> **1. 21+ where lawful.** If gambling is causing you harm, the National
> Problem Gambling Helpline is **1-800-522-4700**, 24/7, free and
> confidential.
>
> **2. No touting.** No selling picks, no "tail me", no affiliate links, no
> DM offers. This is the one rule that gets an immediate ban rather than a
> warning, and it applies to us as much as to you.
>
> **3. Nothing here is a recommendation to bet.** We take no wagers, hold no
> funds, and are not affiliated with any league, team or sportsbook. Prices
> move constantly and are only accurate as of the timestamp on the post.
>
> **4. Ask anything in #questions.** Nobody here has to already know what vig
> means.

---

## What is deliberately not here

**No @everyone on posts.** A price feed that notifies every member every two
hours trains people to mute the channel, and a muted channel is a dead one.

**No invite links in this file.** They belong wherever you actually promote
the server.

**No welcome bot, no levelling, no reaction roles.** Every one of those is a
thing to maintain before there is anyone to maintain it for.

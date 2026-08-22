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

## 2. Channels — paste-ready

Six channels in four categories. Create them top to bottom; Discord orders them
in creation order. Each **topic** goes in Edit Channel → Topic and is what a new
member reads under the channel name before they read anything else.

Fewer than feels natural, on purpose. An empty channel reads as a dead server.

### INFORMATION  *(category)*

**`start-here`** — read-only
> What Sooth is, how to read a price, and what we don't claim. Start here.

**`the-rules`** — read-only
> Four rules. The one about touting is the one that gets you removed.

### THE BOARD  *(category)*

**`line-movement`** — read-only, free webhook posts here
> Books currently pricing away from the cross-book consensus, on games that
> haven't started. A gap between prices, not a forecast.

### COMMUNITY  *(category)*

**`general`** — members can post
> Anything. Keep it civil, keep it legal, no touting.

**`questions`** — members can post
> Ask anything, including the basics. Nobody here has to already know what vig
> means.

### PRO  *(category — private, restricted to the Pro role)*

**`pro-movement`** — read-only, Pro webhook posts here
> The same movement feed plus game lines — moneylines, spreads and totals, not
> only player props.

**`pro-slate`** — read-only
> The sealed weekly slate at seal time. It unlocks free for everyone at first
> kickoff — Pro buys timing, not accuracy. Our model loses to the closing
> market and the record is on the page that sells this.

**Read-only setup**, for every channel marked read-only:
Edit Channel → Permissions → @everyone → **Send Messages: off**, View Channel: on.

**Private category setup**, for PRO:
Edit Category → Permissions → @everyone → **View Channel: off**, then add the
Pro role with View Channel: on. Create the role first under Server Settings →
Roles → **Pro**.

Do not create channels you have nothing to put in yet. `#line-moves`,
`#injuries`, `#nfl` and the rest can exist the day something posts to them.

## 3. Webhooks

Two, because the bot already supports a free and a paid tier and you will not
want to retrofit that later.

`#line-movement` → **Edit Channel → Integrations → Webhooks → New Webhook**

- Name: `Sooth`
- Copy the URL. **Do not paste it into a chat window or a file in this repo.**

Repeat in `#pro-movement` for the second webhook. The bot reads two separate
secrets and sends the free feed and the Pro feed to different channels.

---

## 4. Store them as GitHub secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `SOOTH_DISCORD_WEBHOOK_FREE` | the `#line-movement` webhook URL |
| `SOOTH_DISCORD_WEBHOOK_PRO` | the `#pro-movement` webhook URL |

These names are what `engine/alert_discord.py` already reads. Nothing else in
the repo has to change to match them.

---

## 5. Merge the bot

**The bot is already on `main`.** `engine/alert_discord.py` and
`.github/workflows/discord.yml` merged on 2026-08-21, before the server existed,
specifically so launching is a webhook and not a merge. With no secrets set it
prints "not configured yet, nothing posted" and exits clean, so the scheduled
runs have been green and empty rather than red and ignored.

The movement feed this channel actually carries is **PR #6**. Check it is
merged before expecting anything to post.

Nothing needs to be added to `POSTABLE` to make the channel work.

**What `POSTABLE` actually gates** is `--mode edges`, which ranks by *model*
edge. It is deliberately empty because the strikeout model measured no edge on
the population books actually post (see `/props-model`), and that mode is now
diagnostic-only and cannot publish under any flag. PRODUCT.md carries "never
rank a price product by model edge" as a hard constraint.

Movement is not that. It ranks on how far one book's price sits from the
cross-book consensus — a fact about prices, with no model in it. Same family as
the best-price selection, which is why neither is gated by `POSTABLE`.

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
> **What we sell, and what we don't**
>
> We sell access and instrumentation. We never sell outcomes.
>
> There is a weekly NFL slate — sealed before kickoff, graded in public, and
> free to everyone once it can be graded. Paid access buys it *earlier*, not
> more accurately. The model behind it **loses to the closing market**: 49.5%
> against the spread over 2,608 graded games, where 52.4% breaks even. That
> figure is on the page that sells it, because a number you only find in the
> small print isn't disclosure.
>
> We also measured a model against player props and it had no edge at all on
> the props books actually post. We published that too, in full, including the
> explanations we got wrong first. <https://sooth.bet/props-model>
>
> Nothing here is a recommendation to bet, and nobody here will tell you who
> wins.
>
> **Reading a post in #line-movement**
>
> Each alert is one book pricing away from where every other book has it, on a
> game that hasn't started. That's a gap between prices — it isn't a
> prediction that the side wins, and we're not telling you to take it.
>
> **The channel is quiet most days.** That's the design, not a fault.
>
> Full explainer: <https://sooth.bet/learn> · The board: <https://sooth.bet>

### `#line-movement`  *(pin this before the first alert)*

> **This channel is quiet by design.**
>
> It fires when a book is 2+ points off the cross-book consensus on a game
> that hasn't started. On a thin slate that's nothing at all, and you'll see
> nothing for a day or two.
>
> A quiet day means the books agree with each other. It does not mean the feed
> is broken, and we would rather post nothing than manufacture something to
> keep the channel busy.
>
> **What an alert is:** one book's price sitting away from where the rest of
> the market has it. A fact about prices.
>
> **What it isn't:** a prediction, a recommendation, or a claim that the side
> wins. We publish a model that loses to the closing market — nothing here is
> that model, and nothing here is a pick.
>
> Prices move fast. By the time you read it the gap may be gone; check the
> book.

### `#pro-slate`  *(pin this before the first slate posts)*

> The slate posts here at seal time and unlocks free for everyone at first
> kickoff. You are paying for the hours in between, and nothing else.
>
> Every slate is graded in public afterwards — the weeks it goes badly are
> published on the same schedule as the weeks it goes well. If that ever stops
> being true, stop paying for this.
>
> Record, in full: <https://sooth.bet/record>

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

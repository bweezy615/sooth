# Multi-Sport Prediction Platform — Data Architecture & Build Plan
**Date:** 2026-08-02 · **Hard deadline:** NFL Week 1, 2026-09-10 (≈5.5 weeks) · **Model:** free public predictions, cryptographically committed, publicly auditable; paid tier at kickoff.

---

## 0. The one architectural decision that drives everything

The verification pass produced a single dominant finding: **almost no free "closing line" is actually a documented closing line.** nflverse `games.csv` is an undocumented periodic snapshot that disagrees with the only documented-close NFL source on 27.8% of 2024 spreads and already carries 2026 lookahead prices. ESPN's `close` object is a frozen last-poll (`close == current` in every sampled 2025 MLB game). tennis-data.co.uk says only "generally … the most recent before play starts." Kaggle UFC `adding_date` is a scrape timestamp.

Therefore:

> **The archive is for backtesting. Our own capture is for grading.**
> From day one, a snapshot cron writes every price we can see into our own store with `observed_at` and a `provenance` label. Public CLV claims are made *only* against rows whose provenance is `documented_close` or `own_capture_prelock`. Everything else grades on results only and says so in the UI.

`provenance` is a first-class column, not a README note. The tier list below is enforced in SQL, not by discipline.

---

## 1. TIER LIST

Tier definitions:

| Tier | Meaning |
|---|---|
| **LIVE** | Publishable + committed + graded on results **and** on an auditable closing line. A real backtest exists on the *same* odds series we will grade with. |
| **CALIBRATING** | Publishable + committed + graded on **results only**. CLV shown as "proxy" or withheld. Badged in UI. Excluded from paid-tier claims. |
| **DEFERRED** | No free odds path, or integration cost exceeds pre-launch value. Shadow ingest only: we store data and run models, publish nothing. |

Tiering is **per (sport × market)**, not per sport. Marking a whole sport Live when only one of its markets has an auditable close is the exact failure mode that makes an "auditable track record" claim collapse under scrutiny.

### LIVE at launch

| Sport | Markets | Closing-line basis | Backtest depth |
|---|---|---|---|
| **NBA** | ML, spread, total | DillonKoch SBR mirror (explicit `Open`/`Close`/`ML` columns) 2007-08→2021-22 + ESPN `close` 2022-23→now. Seam verified clean (2022-01-15 = 0 close/SBR covers it; 2022-10-18 opener = 2/2 close). | 19 seasons, ~24k games, 100% game-level close coverage in ESPN era |
| **NHL** | ML, puckline, total, reg-60 3-way | SBR HTML archive (literal `Open`/`Close`/`OpenOU`/`CloseOU` headers, browser-UA required) 2007-08→2021-22 + ESPN `close` 2022-23→now | 19 seasons; puckline only 2019-20+ |
| **EPL** | 1X2 | football-data.co.uk `PSCH/PSCD/PSCA`. **`notes.txt` documents the close explicitly**: C-inserted columns are closing odds. 380/380 rows populated from 2012/13. | 14 seasons 1X2 |
| **EPL** | Asian handicap, O/U 2.5 | `AHCh` + `B365CAHH/PCAHH/AvgCAHH`, `B365C>2.5` etc. First season 2019/20. | 7 seasons |
| **NFL** | **Spread + Total ONLY** | covers.com/sportsoddshistory — the only NFL source that self-documents as closing ("Odds courtesy of Pro-Football-Reference.com and are the closing odds"), 1977→2025. HTML scrape, 301 from the old domain. | 48 seasons available; model on 2006+ |

NFL is the launch anchor and it ships Live — but **spread and total only**, graded against covers/SOH, with 2026 in-season closes captured by our own ESPN cron (ESPN publishes open/close blocks only for *upcoming* games; completed slates return no odds, so backfill is impossible — this is the single most time-critical engineering item on the calendar).

### CALIBRATING at launch

| Sport | Markets | Why not Live |
|---|---|---|
| **NFL** | Moneyline | No free documented closing ML history. `games.csv` ML is undocumented, pre-dates DraftKings by 12 years, and disagrees with the repo's own `closing_lines.csv` on 2,647/3,232 home MLs. SOH carries no ML. Promote once our own capture accumulates a season. |
| **MLB** | ML, run line, total | Hard 2020–2022 gap, ~50% 2023 gap. 2014–2019 comes from `pwu97/bettingtools` — dead since 2020, license NOASSERTION (**do not ship in a paid product until legal review**). 2024+ is single-book ESPN BET with `close == current`. |
| **UFC** | ML, method-of-victory | Real timestamped multi-book lines exist only Mar 2025→now (~17 months, 1,559 fights). Near-event coverage is 65.8%, not 73%. Pre-2025 = 6,299 rows, one anonymous decimal per fight, all stamped with a single bulk-load timestamp. |
| **Tennis (ATP+WTA)** | ML | tennis-data.co.uk odds are "generally the most recent before play starts" — undocumented, no timestamp, no open/close pair. `MaxW/AvgW` are Oddsportal cross-book aggregates of unknown timing. Also: Pinnacle fill collapses to 4.1% in 2026. Huge free result archive makes it worth publishing *results-graded* predictions. |

### DEFERRED (shadow ingest only)

| Sport | Why |
|---|---|
| **F1** | No free, no-auth closing odds. Betfair Historic BASIC is free-of-charge but **account-gated and unavailable in most US jurisdictions** — verifier could not open the spec at all (403). Ingest jolpica + F1DB + FastF1 now so ratings converge; publish nothing until we have ≥1 season of own-captured Betfair/OddsAPI prices. |
| **Cricket** | Confirmed `closing_odds: false`. No cricket equivalent of football-data.co.uk exists. Cricsheet is excellent for results/ball-by-ball but `ipl_csv2.zip` was 7 weeks stale on inspection — pin pipelines to `all_json.zip`, not the per-competition CSVs. |
| **NHL/NBA player props, NFL props, EPL alt-lines** | No free graded history anywhere. Out of scope through 2027. |

### Launch scoreboard
- **5 sport×market families Live** (NBA, NHL, EPL×2, NFL spread/total)
- **4 Calibrating** (NFL ML, MLB, UFC, Tennis)
- **2 Deferred** (F1, Cricket) → 9 sports covered, 7 published.

---

## 2. UNIFIED SCHEMA

Postgres 16. The core generalization:

> **A market is an n-way categorical distribution over `outcome_key`s, n ≥ 2.** Two-sided matchups are the n=2 special case; 1X2 is n=3; an F1 race winner market is n=20. Do not build a `home_team`/`away_team` schema and then bolt racing on — invert it.

### 2a. Reference / entities

```sql
CREATE TABLE sport (
  sport_id        TEXT PRIMARY KEY,           -- 'nfl','nba','mlb','nhl','epl','ufc','f1','atp','wta','cricket'
  display_name    TEXT        NOT NULL,
  contest_shape   TEXT        NOT NULL,       -- 'two_sided' | 'field'
  tier            TEXT        NOT NULL,       -- 'live'|'calibrating'|'deferred'
  default_markets TEXT[]      NOT NULL
);

CREATE TABLE source (
  source_id      TEXT PRIMARY KEY,            -- 'nflverse','espn_core','espn_site','sbr_mirror_nba',
                                              -- 'covers_soh','fdcouk','cricsheet','kaggle_ufc','jolpica',...
  base_url       TEXT NOT NULL,
  auth_kind      TEXT NOT NULL,               -- 'none'|'browser_ua'|'api_key'|'account'
  license        TEXT NOT NULL,               -- 'mit'|'cc0'|'noassertion'|'scrape_tos_grey'
  commercial_ok  BOOLEAN NOT NULL,            -- gate: false ⇒ dev/backtest only, never in paid product
  is_live_feed   BOOLEAN NOT NULL,            -- false ⇒ frozen archive, one-time load
  last_seen_ok   TIMESTAMPTZ
);

CREATE TABLE entity (
  entity_id      BIGSERIAL PRIMARY KEY,
  sport_id       TEXT NOT NULL REFERENCES sport,
  entity_type    TEXT NOT NULL,               -- 'team'|'fighter'|'driver'|'constructor'|'player'
  canonical_name TEXT NOT NULL,
  country        TEXT,
  dob_or_founded DATE,
  meta           JSONB NOT NULL DEFAULT '{}',
  UNIQUE (sport_id, entity_type, canonical_name)
);

CREATE TABLE entity_alias (
  alias_id    BIGSERIAL PRIMARY KEY,
  entity_id   BIGINT NOT NULL REFERENCES entity,
  source_id   TEXT   NOT NULL REFERENCES source,
  source_key  TEXT   NOT NULL,                -- source's id, or normalize(name)
  alias_kind  TEXT   NOT NULL,                -- 'id'|'name'|'abbrev'
  valid_from  DATE, valid_to DATE,            -- handles OAK→LV, SD→LAC, STL→LA, club renames
  confidence  REAL   NOT NULL DEFAULT 1.0,
  UNIQUE (source_id, source_key, alias_kind, valid_from)
);

CREATE TABLE venue (
  venue_id   BIGSERIAL PRIMARY KEY,
  name       TEXT NOT NULL,
  city       TEXT, country TEXT,
  lat        NUMERIC(9,6), lon NUMERIC(9,6), elevation_m INT,
  roof       TEXT,                             -- 'outdoor'|'dome'|'retractable_closed'|'retractable_open'|'indoor'
  surface    TEXT,
  tz         TEXT NOT NULL                     -- IANA
);
```

### 2b. Events & contestants

```sql
CREATE TABLE event (
  event_id        BIGSERIAL PRIMARY KEY,
  sport_id        TEXT        NOT NULL REFERENCES sport,
  natural_key     TEXT        NOT NULL,        -- 'nfl:2026_01_KC_BAL', 'ufc:401901849', 'f1:2026_11_race'
  season          TEXT        NOT NULL,        -- '2026' | '2025-26' | '2025/26'  (string; sports disagree)
  season_phase    TEXT        NOT NULL,        -- 'pre'|'reg'|'post'|'friendly'
  round_label     TEXT,                        -- 'W3','R64','Matchday 5','Round 11'
  parent_event_id BIGINT      REFERENCES event,-- UFC card / F1 GP weekend / tennis tournament
  scheduled_start TIMESTAMPTZ NOT NULL,        -- ALWAYS UTC
  lock_ts         TIMESTAMPTZ NOT NULL,        -- prediction cutoff (see §2f)
  status          TEXT        NOT NULL,        -- 'scheduled'|'in_progress'|'final'|'postponed'|'void'
  venue_id        BIGINT      REFERENCES venue,
  neutral_site    BOOLEAN     NOT NULL DEFAULT FALSE,
  contest_shape   TEXT        NOT NULL,        -- copied from sport, overridable per event
  n_contestants   SMALLINT    NOT NULL,
  meta            JSONB       NOT NULL DEFAULT '{}',
  UNIQUE (sport_id, natural_key)
);
CREATE INDEX ON event (sport_id, scheduled_start);
CREATE INDEX ON event (lock_ts) WHERE status = 'scheduled';

CREATE TABLE contestant (
  contestant_id BIGSERIAL PRIMARY KEY,
  event_id      BIGINT   NOT NULL REFERENCES event ON DELETE CASCADE,
  entity_id     BIGINT   NOT NULL REFERENCES entity,
  slot          SMALLINT NOT NULL,             -- 0,1 two-sided; 0..N-1 field
  role          TEXT     NOT NULL,             -- 'home'|'away'|'red'|'blue'|'p1'|'p2'|'entrant'
  is_host       BOOLEAN  NOT NULL DEFAULT FALSE,
  starting_pos  REAL,                          -- F1 grid; NULL elsewhere
  meta          JSONB    NOT NULL DEFAULT '{}',-- starting QB id, probable pitcher, goalie prob,
                                               -- weight class, XI list, constructor_entity_id
  UNIQUE (event_id, slot)
);
```

### 2c. Markets & outcomes (the n-way generalization)

```sql
CREATE TABLE market (
  market_id     BIGSERIAL PRIMARY KEY,
  event_id      BIGINT   NOT NULL REFERENCES event ON DELETE CASCADE,
  market_type   TEXT     NOT NULL,  -- 'ml_2way','ml_3way','handicap','total',
                                    -- 'outright_win','podium','h2h_pair','method','rank_top_n'
  period        TEXT     NOT NULL DEFAULT 'full',  -- 'full'|'reg60'|'h1'|'inn1'
  line          NUMERIC(6,2),       -- spread/handicap/total value; NULL for ml/outright
  line_ref_slot SMALLINT,           -- handicap quoted relative to this contestant slot
  pair_slots    SMALLINT[],         -- for 'h2h_pair' in field sports: exactly 2 slots
  n_outcomes    SMALLINT NOT NULL,
  UNIQUE (event_id, market_type, period, line, line_ref_slot, pair_slots)
);

CREATE TABLE market_outcome (
  outcome_id    BIGSERIAL PRIMARY KEY,
  market_id     BIGINT NOT NULL REFERENCES market ON DELETE CASCADE,
  outcome_key   TEXT   NOT NULL,    -- 'slot0','slot1','draw','over','under',
                                    -- 'slot0_ko','slot0_sub','slot0_dec','slot1_ko',...
  contestant_id BIGINT REFERENCES contestant,  -- NULL for draw/over/under
  UNIQUE (market_id, outcome_key)
);
```

### 2d. Odds

```sql
CREATE TABLE odds_snapshot (
  snapshot_id   BIGSERIAL PRIMARY KEY,
  outcome_id    BIGINT      NOT NULL REFERENCES market_outcome,
  book_id       TEXT        NOT NULL,  -- 'pinnacle','draftkings','espnbet','betfair_ex',
                                       -- 'sbr_consensus','oddsportal_avg','oddsportal_max','unknown'
  price_decimal NUMERIC(10,4) NOT NULL, -- ALWAYS decimal internally; convert American at the edge
  line_at_snap  NUMERIC(6,2),           -- lines move; never assume market.line
  observed_at   TIMESTAMPTZ NOT NULL,   -- when WE saw it
  book_ts       TIMESTAMPTZ,            -- book's own stamp if published (almost always NULL)
  source_id     TEXT        NOT NULL REFERENCES source,
  capture_mode  TEXT        NOT NULL,   -- 'live_poll'|'archive_backfill'
  provenance    TEXT        NOT NULL,   -- see enum below
  raw_ref       TEXT                    -- s3://raw/<source>/<sha256>.json.gz
);
CREATE INDEX ON odds_snapshot (outcome_id, observed_at DESC);
CREATE INDEX ON odds_snapshot (source_id, observed_at);
```

`provenance` enum, in descending trust order:

| value | meaning | CLV-gradeable? |
|---|---|---|
| `documented_close` | Source explicitly labels it closing (fdcouk `PSC*`, SBR `Close`, covers/SOH) | **yes** |
| `own_capture_prelock` | Our cron, `0 ≤ lock_ts − observed_at ≤ 3600s` | **yes** |
| `last_poll_frozen` | ESPN `close` object (= last poll, undocumented cutoff) | proxy only |
| `undocumented_snapshot` | nflverse `games.csv`, tennis-data pre-match | proxy only |
| `aggregate_unknown_time` | Oddsportal `Max`/`Avg`, SBR consensus | proxy only |
| `bulk_unlabeled` | Kaggle UFC `zewnetrzne`, single bulk stamp | **no** |

```sql
-- Resolved close, one row per (outcome, book). Rebuilt by the settlement job.
CREATE TABLE closing_line (
  outcome_id     BIGINT      NOT NULL REFERENCES market_outcome,
  book_id        TEXT        NOT NULL,
  price_decimal  NUMERIC(10,4) NOT NULL,
  line_value     NUMERIC(6,2),
  observed_at    TIMESTAMPTZ NOT NULL,
  lag_seconds    INTEGER     NOT NULL,  -- lock_ts - observed_at; <0 ⇒ post-lock ⇒ reject
  provenance     TEXT        NOT NULL,
  grade_eligible BOOLEAN     NOT NULL,  -- provenance='documented_close'
                                        --   OR (provenance='own_capture_prelock' AND lag_seconds BETWEEN 0 AND 3600)
  PRIMARY KEY (outcome_id, book_id)
);

-- Devigged market consensus — the benchmark every model is scored against.
CREATE TABLE market_consensus (
  market_id    BIGINT NOT NULL REFERENCES market,
  outcome_id   BIGINT NOT NULL REFERENCES market_outcome,
  p_devig      NUMERIC(8,7) NOT NULL,
  devig_method TEXT NOT NULL,          -- 'proportional'|'shin'|'power'|'log'
  overround    NUMERIC(6,4) NOT NULL,
  n_books      SMALLINT NOT NULL,
  grade_eligible BOOLEAN NOT NULL,
  PRIMARY KEY (outcome_id)
);
```

### 2e. Predictions, commitment, grading

```sql
CREATE TABLE prediction (
  prediction_id  BIGSERIAL PRIMARY KEY,
  market_id      BIGINT      NOT NULL REFERENCES market,
  model_id       TEXT        NOT NULL,   -- 'nba_elo4f_v2'
  model_version  TEXT        NOT NULL,   -- git sha of the training commit
  created_at     TIMESTAMPTZ NOT NULL,
  feature_asof   TIMESTAMPTZ NOT NULL,   -- CHECK (feature_asof <= (SELECT lock_ts FROM event ...))
  uses_market_features BOOLEAN NOT NULL, -- TRUE ⇒ may not claim "beat the close"
  salt           BYTEA       NOT NULL,   -- 32 random bytes, revealed at settlement
  commitment_id  BIGINT      REFERENCES commitment,
  UNIQUE (market_id, model_id, model_version)
);

CREATE TABLE prediction_outcome (
  prediction_id BIGINT NOT NULL REFERENCES prediction ON DELETE CASCADE,
  outcome_id    BIGINT NOT NULL REFERENCES market_outcome,
  p_raw         NUMERIC(8,7) NOT NULL,   -- model output
  p_cal         NUMERIC(8,7) NOT NULL,   -- post-calibration, renormalized: SUM(p_cal)=1 per prediction
  PRIMARY KEY (prediction_id, outcome_id)
);

CREATE TABLE commitment (
  commitment_id      BIGSERIAL PRIMARY KEY,
  merkle_root        BYTEA       NOT NULL,
  leaf_count         INT         NOT NULL,
  hash_algo          TEXT        NOT NULL DEFAULT 'sha256',
  built_at           TIMESTAMPTZ NOT NULL,
  published_at       TIMESTAMPTZ,
  covers_lock_after  TIMESTAMPTZ NOT NULL, -- batch window
  covers_lock_before TIMESTAMPTZ NOT NULL, -- MUST be > NOW() at publish time
  anchor_kind        TEXT,                 -- 'git_tag'|'opentimestamps'|'x_post'|'ipfs_cid'
  anchor_ref         TEXT
);
```

Leaf = `sha256(canonical_json({prediction_id, market natural key, model_id, model_version, feature_asof, [(outcome_key, p_cal)] sorted}) || salt)`. Root published **before** `covers_lock_after`. Salts + leaves revealed after settlement so any third party can recompute the root. Never commit a batch that contains an already-locked event — the batch builder must `SELECT ... WHERE lock_ts > now() + interval '10 minutes'`.

```sql
CREATE TABLE event_result (
  event_id     BIGINT PRIMARY KEY REFERENCES event,
  status       TEXT        NOT NULL,   -- 'final'|'void'|'no_contest'|'abandoned'|'draw'
  finalized_at TIMESTAMPTZ NOT NULL,
  score        JSONB       NOT NULL,   -- {"slot0":24,"slot1":17,"periods":[[7,3],[10,7],...]}
  detail       JSONB       NOT NULL,   -- method+round (UFC), finishing_order[] (F1),
                                       -- went_to_OT/SO (NHL), DLS flag (cricket), retirement (tennis)
  source_id    TEXT        NOT NULL REFERENCES source
);

CREATE TABLE outcome_settlement (
  outcome_id BIGINT PRIMARY KEY REFERENCES market_outcome,
  result     SMALLINT    NOT NULL,     -- 1 | 0
  is_push    BOOLEAN     NOT NULL DEFAULT FALSE,
  is_void    BOOLEAN     NOT NULL DEFAULT FALSE,
  settled_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE prediction_grade (
  prediction_id BIGINT PRIMARY KEY REFERENCES prediction,
  brier         NUMERIC(9,7),   -- multiclass: SUM_k (p_k - y_k)^2
  log_loss      NUMERIC(9,6),
  brier_skill   NUMERIC(9,6),   -- 1 - brier/brier_market_consensus  (the real number)
  clv_bps       INTEGER,        -- 10000*(p_cal/p_devig_close - 1) on our top pick; NULL if not eligible
  beat_close    BOOLEAN,
  close_book    TEXT,
  grade_basis   TEXT NOT NULL,  -- 'documented_close'|'own_capture'|'proxy_close'|'result_only'
  graded_at     TIMESTAMPTZ NOT NULL
);
```

### 2f. How racing and combat fit

**F1 (field, n=20).** `event.contest_shape='field'`, `n_contestants=20`, `parent_event_id` → the GP weekend. 20 `contestant` rows, `role='entrant'`, `is_host=false`, `starting_pos` = grid slot (distinct from qualifying position — grid penalties). One `market` row `market_type='outright_win'`, `n_outcomes=20`, with 20 `market_outcome` rows each pointing at a `contestant_id`. Podium = a second market `market_type='podium'` with 20 outcomes where `outcome_settlement.result=1` for three of them (a multi-label market — flagged by `n_outcomes > 1 winner` in settlement, and scored with per-outcome Brier rather than multiclass). Driver-vs-driver head-to-head = `market_type='h2h_pair'`, `pair_slots={3,7}`, `n_outcomes=2`. **Zero schema change; the "two sides" of a two-sided market are just slots 0 and 1 of a degenerate field.**

**UFC (two-sided, neutral).** `event` = one bout; `parent_event_id` = the card. `n_contestants=2`, roles `red`/`blue`, `is_host=false` for both, `neutral_site=true`. `ml_2way` with outcomes `slot0`/`slot1` (add `draw` → n=3 only for the ~0.3% of bouts that can draw; we model draw explicitly and settle draws as `is_void=true` on ML per standard book rules). Method-of-victory is `market_type='method'`, `n_outcomes=6` (`slot0_ko`, `slot0_sub`, `slot0_dec`, `slot1_*`) — a genuine n-way market that a home/away schema could not express. No `handicap` rows ever exist for `sport_id='ufc'`; absence is the representation, no nullable columns needed.

**Tennis** is structurally identical to UFC (`p1`/`p2`, neutral) plus a `Comment`-derived `is_void` path for retirements/walkovers, which book settlement rules treat inconsistently — we record `detail->>'retirement_set'` and grade retirements as void.

**Cricket** uses `ml_3way` (`slot0`/`draw`/`slot1`) for Tests, `ml_2way` for limited-overs, and `total` with `period='inn1'` for first-innings runs. `lock_ts` = **toss time (T−30m)**, not first ball — that is when XIs confirm and when the market moves; a pre-toss and a post-toss prediction are different products and must be different `model_id`s.

**`lock_ts` by sport** (the field that makes CLV honest):

| Sport | lock_ts |
|---|---|
| NFL / NBA / NHL / MLB / EPL | scheduled kickoff/tip/puck-drop/first-pitch |
| UFC | card main-card start (individual bout start is unknowable in advance) — accept the wider window explicitly |
| F1 | lights out (`Race.time` from jolpica) |
| Tennis | scheduled session start, **not** match start (match start depends on preceding matches) — this is why tennis CLV is structurally unreliable and tennis is Calibrating |
| Cricket | toss (`scheduled_start − 30m`) |

---

## 3. ADAPTER INTERFACE

One engine, N adapters. Python 3.12, `typing.Protocol`. The engine never imports a sport-specific module directly; adapters register via entry point `predplat.adapters`.

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Iterator, Sequence, Literal, Mapping, Any

Provenance = Literal["documented_close","own_capture_prelock","last_poll_frozen",
                     "undocumented_snapshot","aggregate_unknown_time","bulk_unlabeled"]

@dataclass(frozen=True, slots=True)
class EntityRef:
    entity_type: str; source_key: str; display: str; confidence: float = 1.0

@dataclass(frozen=True, slots=True)
class ContestantRec:
    slot: int; role: str; entity: EntityRef
    is_host: bool = False; starting_pos: float | None = None
    meta: Mapping[str, Any] = ()

@dataclass(frozen=True, slots=True)
class EventRec:
    natural_key: str; season: str; season_phase: str; round_label: str | None
    scheduled_start: datetime; lock_ts: datetime; status: str
    contest_shape: Literal["two_sided","field"]
    contestants: tuple[ContestantRec, ...]
    venue_key: str | None = None; neutral_site: bool = False
    parent_natural_key: str | None = None
    meta: Mapping[str, Any] = ()

@dataclass(frozen=True, slots=True)
class MarketRec:
    market_type: str; period: str = "full"
    line: float | None = None; line_ref_slot: int | None = None
    pair_slots: tuple[int, ...] | None = None
    outcome_keys: tuple[str, ...] = ()
    outcome_slots: tuple[int | None, ...] = ()   # parallel to outcome_keys

@dataclass(frozen=True, slots=True)
class OddsQuote:
    event_natural_key: str; market: MarketRec; outcome_key: str
    book_id: str; price_decimal: float; line_at_snap: float | None
    observed_at: datetime; book_ts: datetime | None
    provenance: Provenance; source_id: str; raw_ref: str | None = None

@dataclass(frozen=True, slots=True)
class ResultRec:
    event_natural_key: str; status: str; finalized_at: datetime
    score: Mapping[str, Any]; detail: Mapping[str, Any]

@dataclass(frozen=True, slots=True)
class Settlement:
    outcome_key: str; result: int; is_push: bool = False; is_void: bool = False

@dataclass(frozen=True, slots=True)
class RefreshJob:
    name: str; cron: str; fn: str          # 'schedule'|'odds_live'|'results'|'features'
    window: tuple[str, str] | None = None  # e.g. ('T-72h','T-0') for pre-lock odds ramp

@dataclass(frozen=True, slots=True)
class HealthReport:
    ok: bool; checks: Mapping[str, bool]; notes: tuple[str, ...]


class SportAdapter(Protocol):
    # ---- identity ----
    sport_id: str
    contest_shape: Literal["two_sided","field"]
    supported_markets: frozenset[str]
    tier: Literal["live","calibrating","deferred"]
    banned_feature_columns: frozenset[str]   # leakage blocklist, CI-enforced

    # ---- discovery / normalization ----
    def list_seasons(self) -> list[str]: ...
    def fetch_schedule(self, season: str, since: datetime | None = None) -> Iterator[EventRec]: ...
    def enumerate_markets(self, ev: EventRec) -> Iterator[MarketRec]: ...
    def lock_ts(self, ev: EventRec) -> datetime: ...

    # ---- entity resolution ----
    def resolve_entity(self, source_id: str, source_key: str,
                       ctx: Mapping[str, Any]) -> EntityRef | None: ...
        # deterministic first (source ids, then exact normalized name),
        # fuzzy last; returns None ⇒ engine writes to the review queue, never drops.

    # ---- odds ----
    def fetch_odds_archive(self, season: str) -> Iterator[OddsQuote]: ...
        # raises NoArchiveAvailable for sports with no free history (F1, cricket)
    def fetch_odds_live(self, event_keys: Sequence[str]) -> Iterator[OddsQuote]: ...
        # every quote MUST carry an honest provenance; lying here is a P0 bug

    # ---- results & settlement ----
    def fetch_results(self, season: str, since: datetime | None = None) -> Iterator[ResultRec]: ...
    def settle(self, market: MarketRec, result: ResultRec) -> list[Settlement]: ...
        # owns push/void semantics: NFL spread push, tennis retirement,
        # cricket DLS/no-result, UFC draw/NC, F1 DNF

    # ---- features (point-in-time enforced) ----
    def feature_asof(self, ev: EventRec) -> datetime: ...
    def build_features(self, ev: EventRec, store: "AsOfStore") -> dict[str, float]: ...
        # `store` is a proxy whose EVERY query is clamped to `WHERE observed_at <= asof`.
        # Adapters must not open their own DB connections or read files directly.

    # ---- ops ----
    def refresh_plan(self) -> list[RefreshJob]: ...
    def healthcheck(self) -> HealthReport: ...
        # asserts each upstream endpoint still returns the expected schema hash
```

Two engine-level guarantees, not adapter concerns:
1. `AsOfStore` makes leakage a type error rather than a code-review question. `build_features` physically cannot see a row with `observed_at > asof`.
2. `banned_feature_columns` is a per-adapter blocklist checked in CI against the feature dict keys and against the source columns each feature reads. Initial contents: NFL `{vegas_wp, vegas_home_wp, vegas_wpa, spread_line, total_line}` when `uses_market_features=False`; NHL `{moneypuck season-summary aggregates}`; Tennis `{MaxW, MaxL, AvgW, AvgL}`.

---

## 4. INGEST PLAN

All raw payloads land in object storage first (`s3://raw/<source_id>/<yyyy>/<mm>/<sha256>.<ext>`) with a manifest row before any parsing. **Every frozen archive is mirrored on day 1 with checksums** — SBRO's live site is already dead; DillonKoch, bettingtools, Sackmann and fastRhockey are all frozen or gone.

### NFL — `live` (spread/total), `calibrating` (ML)
```bash
# results + schedule + features (daily 06:00 ET)
curl -sfL -o raw/nfl/games.csv \
  https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv          # 7,548 rows, 46 cols
for y in $(seq 1999 2025); do
  curl -sfL -o raw/nfl/pbp_$y.parquet \
    https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_$y.parquet
done
for f in injuries snap_counts depth_charts weekly_rosters espn_data pfr_advstats ftn_charting; do :; done
curl -sfL -o raw/nfl/injuries_2026.csv    https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.csv
curl -sfL -o raw/nfl/snap_counts_2026.csv https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_2026.csv
curl -sfL -o raw/nfl/qbr_week.csv         https://github.com/nflverse/nflverse-data/releases/download/espn_data/qbr_week_level.csv
curl -sfL -o raw/nfl/win_totals.csv       https://raw.githubusercontent.com/nflverse/nfldata/master/data/win_totals.csv
curl -sfL -o raw/nfl/airports.csv         https://raw.githubusercontent.com/nflverse/nfldata/master/data/airports.csv

# CLOSING LINES (documented) — spread + total only, 1977-2025. Note the 301 to covers.com.
for y in $(seq 1977 2025); do
  curl -sfL -A 'Mozilla/5.0' -o raw/nfl/soh_$y.html \
    "https://www.covers.com/sportsoddshistory/nfl-game-season/?y=$y"
done
```
- `games.csv` betting columns ingest as `provenance='undocumented_snapshot'`. **Never** graded as close.
- SOH/covers ingest as `provenance='documented_close'`, `book_id='pfr_consensus'`.
- Column order is `under_odds, over_odds` (the claim had it reversed). 2007 is a juice gap year (266/267); 2006 O/U juice is 217/267.
- **In-season (P0, week 1 of build):** ESPN scoreboard snapshot cron.
  `https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?dates=YYYYMMDD&limit=100`
  every 15 min from T−72h, every 60s from T−30m to `lock_ts`. Completed slates return no odds — **there is no backfill.** Miss the cron, lose the week permanently.

### NBA — `live`
```bash
# archive close, 2007-08 .. 2021-22 (15 files; note %20 in filenames)
for s in 2007-08 2008-09 2009-10 2010-11 2011-12 2012-13 2013-14 2014-15 2015-16 \
         2016-17 2017-18 2018-19 2019-20 2020-21 2021-22; do
  curl -sfL -o "raw/nba/sbr_$s.xlsx" \
    "https://raw.githubusercontent.com/DillonKoch/Sports_Betting/master/Data/Odds/NBA/NBA%20odds%20$s.xlsx"
done
# results 2002-03+ : season index then per-date scoreboard
curl -sfL "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2024/types/2/events?limit=1000"
curl -sfL "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20240115"
# per-event close, 2022-23+
curl -sfL "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/events/{id}/competitions/{id}/odds"
```
- SBR parser gotchas: **visitor row = TOTAL, home row = SPREAD** in `Open`/`Close`; `'pk'` is a literal string; `Date` is `MMDD` needing season-year inference across the Dec→Jan rollover.
- ESPN close depth is **1 book** in 2022-23 (ESPN BET), 2024-25 and 2025-26; only 2023-24 is genuinely multi-book (~11). `'ESPN Bet - Live Odds'` (provider 59) has **no** `close` key — filter it or you'll write nulls.
- Cadence: scoreboard every 10 min T−24h→lock, 60s T−15m→lock; per-event odds on the same ramp; results 30 min after final.

### NHL — `live`
```bash
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36'
for s in 2007-08 2008-09 2009-10 2010-11 2011-12 2012-13 2013-14 2014-15 2015-16 \
         2016-17 2017-18 2018-19 2019-20 2021 2021-22; do
  curl -sfL -A "$UA" -o "raw/nhl/sbr_$s.html" \
    "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nhl-odds-$s"
done
curl -sfL "https://api-web.nhle.com/v1/schedule/2026-10-08"
curl -sfL "https://api-web.nhle.com/v1/gamecenter/2025020001/play-by-play"     # x/y coords 2010-11+
curl -sfL "https://api.nhle.com/stats/rest/en/team/summary?cayenneExp=seasonId=20252026"
curl -sfL -A "$UA" "https://moneypuck.com/moneypuck/playerData/seasonSummary/2025/regular/teams.csv"
```
- **Bare curl UA gets HTTP 404 from SBR** and a license-nag page from MoneyPuck. Browser UA + ≥1s delay required.
- SBR header exposes 13 labels but rows carry 16 cells (`PuckLine`, `OpenOU`, `CloseOU` each span line+price). Positional parse, not header-zip.
- 2022-23 SBR page truncates at 11/27 — use ESPN from 2022-23 opener, discard the SBR stub.
- **ESPN `dates=YYYYMMDD` is UTC-keyed**: US evening games appear under the next UTC day. Query `[d, d+1]` and filter on local date, or you drop most of every slate.
- Build our own xG from `/gamecenter/{id}/play-by-play` coordinates rather than depending on MoneyPuck — MoneyPuck's ToS asks for a commercial data licence.

### EPL — `live`
```bash
for s in 9394 9495 ... 2425 2526; do
  curl -sfL -o raw/epl/E0_$s.csv "https://www.football-data.co.uk/mmz4281/$s/E0.csv"
done
curl -sfL -o raw/epl/notes.txt   https://www.football-data.co.uk/notes.txt
curl -sfL -o raw/epl/fixtures.csv https://www.football-data.co.uk/fixtures.csv   # all divisions; filter Div=='E0'
```
- Read with `encoding='utf-8-sig'` (BOM), dates `DD/MM/YYYY`.
- **Parse headers per season.** Schema drifts 106→120→132 cols. `WHCH`/`1XBCH` exist in 2019/20 and are gone by 2025/26. Never hardcode a book list.
- 9394 has 7 named columns, no odds, and **90 blank trailing comma-rows** after 462 real matches — filter `Div=='E0'`.
- Closing 1X2 starts 2012/13 (`PSCH`); AH + O2.5 close starts 2019/20 (`AHCh`, `B365CH`).
- Cadence: `fixtures.csv` every 30 min (closing cols are blank until match close — poll and snapshot ourselves); `E0.csv` post-matchday for results.

### MLB — `calibrating`
```bash
for y in $(seq 1990 2026); do curl -sfL -o raw/mlb/gl$y.zip "https://www.retrosheet.org/gamelogs/gl$y.zip"; done
curl -sfL "https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=2026-08-03&hydrate=probablePitcher,weather,lineups"
curl -sfL "https://statsapi.mlb.com/api/v1.1/game/{gamePk}/feed/live"
curl -sfL "https://baseballsavant.mlb.com/statcast_search/csv?all=true&type=details&game_date_gt=2026-08-01&game_date_lt=2026-08-01"
curl -sfL "https://sports.core.api.espn.com/v2/sports/baseball/leagues/mlb/events/{id}/competitions/{id}/odds"
# 2014-2019 backfill — QUARANTINED, license NOASSERTION, backtest-only
curl -sfL -o raw/mlb/_quarantine/mlb_odds_2019.rda \
  https://raw.githubusercontent.com/pwu97/bettingtools/master/data/mlb_odds_2019.rda
```
- **Parser trap:** `close.total.value` is `0.0`; the real total is in `close.total.alternateDisplayValue`.
- 2024+ is one book (ESPN BET) and `close == current`. Provenance `last_poll_frozen`.
- Quarantine bucket is excluded from any artifact that ships to a paying customer until licensing is resolved.
- Cadence: schedule + probables 08:00 local; odds every 15 min from T−12h, 60s from T−20m; results 20 min post-final.

### UFC — `calibrating`
```bash
curl -sfL -o raw/ufc/odds.zip \
  https://www.kaggle.com/api/v1/datasets/download/jerzyszocik/ufc-betting-odds-daily-dataset   # 302→GCS, ~2.3MB
for f in ufc_fight_results ufc_event_details ufc_fight_stats ufc_fighter_tott ufc_fighter_details; do
  curl -sfL -o raw/ufc/$f.csv "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/$f.csv"
done
curl -sfL "https://site.api.espn.com/apis/site/v2/sports/mma/ufc/scoreboard?dates=20260801-20260930"
```
- **Join is the whole job.** 63% of live odds rows have blank `fight_url`; **100% of 2026+ rows have none.** Fuzzy match on `(normalize(fighter_1), normalize(fighter_2), event_date ±2d)` into `entity_alias`, with a manual review queue. Enforce a ≥98% join-rate SLO.
- `ufc_fight_results.csv` has **no date column**; dates come from `ufc_event_details.csv` joined on `EVENT` — and the results file's EVENT strings have **trailing whitespace**. `strip()` before joining.
- Book identity lives in `source`, not a `sportsbook` column; `region` is contaminated with book slugs. `event_date` max is 2027-08-01 (placeholder junk) — drop rows beyond `now()+400d`.
- ESPN MMA has **no odds endpoint** (`.../mma/leagues/ufc/events/{id}/.../odds` → 404). Schedule/results only.
- Cadence: Kaggle re-pull daily 16:00 UTC (their cron lands ~15:45); our own capture is impossible without a book scraper — accept `bulk_unlabeled` + `last_poll` and badge accordingly.

### Tennis — `calibrating`
```bash
UA='Mozilla/5.0 ...'
for y in $(seq 2000 2026); do curl -sfL -A "$UA" -o raw/atp/$y.xlsx "http://www.tennis-data.co.uk/$y/$y.xlsx"; done
for y in $(seq 2007 2026); do curl -sfL -A "$UA" -o raw/wta/$y.xlsx "http://www.tennis-data.co.uk/${y}w/$y.xlsx"; done
curl -sfL "https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard?dates=20260801"
curl -sfL -o raw/atp/sackmann_2024.csv \
  https://raw.githubusercontent.com/jegqwll/tennis_atp_2000_2025/main/atp_matches_2024.csv
```
- **WTA loop must start at 2007.** Years 2001-2006 on the `w` pattern return **byte-identical ATP files, not 404** — a naive loop silently ingests 6 seasons of men's matches labelled WTA.
- 2000-2012 files are legacy OLE2 `.xls` served with a `.xlsx` extension → `xlrd`, not `openpyxl`. **Validate magic bytes** (`D0CF11E0` vs `504B0304`); the server intermittently returns 504 with a 489-byte HTML body that a naive downloader saves as `.xlsx`.
- Dates pre-2013 are Excel serials; pre-2003 every match carries the tournament start date.
- Pinnacle fill is 4.1% in 2026 (95.8% in 2025) — the sharp reference is gone this season. Use `B365` + `Max`/`Avg` (≈100%) as the spine, and label them `aggregate_unknown_time`.

### F1 / Cricket — `deferred`, shadow ingest
```bash
curl -sfL "https://api.jolpi.ca/ergast/f1/2026/races.json?limit=100"      # 4 rps / 500 rph, no key
curl -sfL -L -o raw/f1/f1db.zip \
  "https://github.com/f1db/f1db/releases/latest/download/f1db-sql-sqlite.zip"
curl -sfL "https://livetiming.formula1.com/static/2026/.../SessionInfo.json"   # FastF1 3.8.3, MIT
curl -sfL -o raw/cricket/all_json.zip https://cricsheet.org/downloads/all_json.zip   # 144 MB
curl -sfL -o raw/cricket/delta.zip    https://cricsheet.org/downloads/recently_played_7_json.zip
curl -sfL -o raw/cricket/people.csv   https://cricsheet.org/register/people.csv
```
- Pin cricket to `all_json.zip` (2-3 day lag) **not** `ipl_csv2.zip` (observed 7 weeks stale).
- `outcome` is always present, `winner` is not (Test draws, no-results) — do not assume label completeness.
- F1 2026 is a new power-unit/aero regulation era: pre-2026 car ratings carry almost no information. Reset constructor priors.

### Refresh cadence summary

| Job | Cadence |
|---|---|
| Schedule sync (all sports) | hourly |
| Odds ramp, tier=live | 15 min from T−72h → 60s from T−30m → `lock_ts` |
| Odds ramp, tier=calibrating | 30 min from T−24h → 5 min from T−1h |
| Results + settlement | every 10 min while any event `in_progress`; sweep at T+6h |
| Commitment batch build+publish | 04:00 UTC daily + ad-hoc ≥10 min before any batch's earliest lock |
| Archive re-mirror + checksum diff | weekly (detects frozen sources going dark) |
| `healthcheck()` schema-hash assertion | every 30 min, pages on failure |

---

## 5. MODELING APPROACH

Every model outputs a **calibrated probability vector over the market's outcome set**, never a pick. Picks are derived downstream by comparing `p_cal` to `market_consensus.p_devig`.

### Devigging (the benchmark)
Default **Shin** for 2- and 3-way (accounts for informed-money share); **power method** for n>3 (F1 outrights, where proportional devig is badly biased on longshots); proportional only as a documented fallback. Method is written to `market_consensus.devig_method` — never silently changed.

### LIVE tier

| Sport | Baseline (ships Week 1) | Upgrade path (post-kickoff) |
|---|---|---|
| **NFL** spread/total | Margin Elo with K≈20, mean-reversion 1/3 to 1500 each offseason, HFA≈2.0 pts, QB adjustment from `away_qb_id`/`home_qb_id` + rolling EPA+CPOE. Cover prob = `Φ((elo_margin − spread)/σ)`, σ≈13.2 with a push mass at key numbers (3, 7, 6, 10, 14). Total = league base + pace/PROE + roof/wind. | Opponent-adjusted EPA ridge (pass/rush, off/def) → GBM on the **residual vs the devigged market**, not on the raw outcome. Market-anchored prior via preseason win totals. |
| **NBA** | Margin Elo + rest/B2B/3-in-4 + travel/altitude, σ≈11.3 around the spread. Total from possession-estimate × opponent-adjusted efficiency. | Opponent-adjusted Four Factors ridge, garbage-time-filtered possessions from PBP, injury-adjusted lineup deltas (requires daily injury snapshotting from day 1 — retroactive reconstruction of who was OUT is impossible). |
| **NHL** | Bivariate Poisson on goals with team attack/defence + HFA, time-decayed. Explicit P(regulation win)/P(OT)/P(SO) so the reg-60 3-way and the full-game ML are consistent. Puckline from the goal-difference distribution, not a normal approx (integers matter at ±1.5). | Own xG from PBP x/y + shot type + strength state; goalie GSAx rolling; score/venue adjustment (mandatory — raw xG is distorted by trailing-team push and 6v5). |
| **EPL** | **Dixon–Coles bivariate Poisson**: attack_i, defence_j, home advantage γ, low-score correlation τ, exponential time decay ξ=0.0065/day (half-life ≈107d). Gives 1X2, AH and O/U 2.5 from one fitted goal matrix — the correct structure for a sport with three outcomes and a correlated scoreline. | Shots/SoT-based attack ratings (real xG is no longer free: understat payload is gone, FBref is Cloudflare-403), promoted-team priors carried forward from E1, hierarchical shrinkage toward market-implied strength. |

### CALIBRATING tier

| Sport | Baseline |
|---|---|
| **MLB** | Log5 / Bradley–Terry team strength + starting-pitcher adjustment from Statcast rolling xERA/CSW%, bullpen-fatigue penalty from trailing 3-day pitch counts, park factor, weather (temp/wind vector from StatsAPI `gameData.weather`). Runs via negative binomial (over-dispersed vs Poisson) for totals. |
| **UFC** | Glicko-2 on 8,810 fights back to the 1990s (long history lets ratings converge before the 2010 odds era) + reach/age/layoff/stance deltas. Method market = multinomial logit over the 6 outcomes with control-time and knockdown-rate features. |
| **Tennis** | Surface-specific Elo (separate hard/clay/grass ratings, blended by a fitted weight) → point-level hold/break model calibrated so serve-hold probabilities reproduce the observed set/match distribution. Fatigue from minutes played in trailing 7/14 days. |
| **NFL ML** | Same Elo as spread, converted to win prob; badged calibrating until we have a season of own-captured closing ML. |

### DEFERRED tier (shadow only)
- **F1:** Plackett–Luce over the field conditioned on grid position, with car (constructor) and driver strength estimated separately via teammate head-to-head — the only clean within-car control. DNF hazard from `reasonRetired`, safety-car base rate per circuit. 2026 regulation reset means priors, not history.
- **Cricket:** venue-conditioned innings-state WP model P(win | runs, wickets, balls left, target) fit on Cricsheet ball-by-ball; toss winner/decision as a first-class feature (resolved 30 min pre-match).

### Calibration
- **Binary markets, n < 2,000 graded samples:** Platt scaling (2-parameter logistic on the logit). Robust at small n; isotonic overfits.
- **Binary markets, n ≥ 2,000:** isotonic regression, fit with **5-fold blocked time-series CV** (blocks = seasons, never shuffled) so the calibrator never sees future games.
- **n-way markets (1X2, UFC method, F1 outright):** single-parameter **temperature scaling** on the softmax logits, then renormalize. One parameter is the only defensible choice when per-outcome sample counts are thin.
- Calibrators are refit **weekly in-season**, versioned, and their fit window is recorded in `model_version`. A calibrator refit is a model version bump and therefore a new commitment.

### Validation
Rolling-origin backtest: train on seasons ≤ S−1, predict S, walk forward. The most recent complete season is held out entirely and never touched until the final go/no-go.

Reported per (sport × market × season):
1. **Multiclass Brier** and **log-loss**.
2. **Brier Skill Score vs the devigged closing line** — `1 − BS_model / BS_market`. This is the only number that matters. Beating 50% is meaningless; beating the close is the product.
3. **Reliability curve**, 10 equal-count bins, with **ECE** and **MCE**. Published as a public chart per sport.
4. **CLV distribution** in bps on graded-eligible rows only, with mean, median, and % positive.
5. Bootstrap 95% CI (2,000 resamples, blocked by game-day to respect same-slate correlation).

### Promotion gate: `calibrating` → `live`
All four must hold on ≥500 graded predictions of own-captured closes:
`BSS_vs_close > 0` with bootstrap CI lower bound `> 0`; `ECE < 0.02`; `mean CLV ≥ 0 bps`; join-rate SLO ≥ 98% for the trailing 30 days. Demotion is automatic and immediate if `ECE > 0.05` or the healthcheck fails for 48h.

---

## 6. RISK REGISTER

### R1 — ESPN's undocumented API is a single point of failure for live odds across NBA, NHL, MLB and NFL
It has no ToS grant, no SLA, no published rate limit, and its close-object depth has already collapsed from ~11 books (2023-24) to 1 (ESPN BET, then DraftKings). One shape change or IP block takes out live grading for four of seven published sports simultaneously.
**Mitigation:** (a) `healthcheck()` asserts a per-endpoint **JSON schema hash** every 30 min and pages on drift — we find out in minutes, not at kickoff. (b) Persist the raw payload to object storage *before* parsing, so a parser break is recoverable and a shape change is diffable. (c) Reserve The Odds API's free 500 credits/month exclusively as an independent cross-check on ~2 games/day per Live sport — not as a feed, as a tripwire that catches ESPN silently serving stale prices. (d) Self-throttle ≤5 concurrent, real User-Agent, aggressive caching. (e) The public track record page degrades gracefully to `grade_basis='result_only'` rather than going blank.

### R2 — The "auditable closing line" claim collapses under a hostile audit
This is the existential risk, because auditability *is* the product. A single blogger who joins our published NFL CLV against covers/SOH and finds 27.8% spread disagreement — or notices we graded 2026 games against lines that existed five weeks before kickoff — ends the paid tier.
**Mitigation:** (a) `provenance` gating in SQL: `prediction_grade.clv_bps` is `NULL` unless `closing_line.grade_eligible`. Not a convention — a constraint. (b) Per-sport **grading-basis badge** rendered on every card: "graded vs documented closing line" / "graded vs our captured pre-kickoff snapshot (T−4m)" / "results only — no verified closing line". (c) Publish the raw captured snapshot (book, price, `observed_at`, our request timestamp) alongside every graded pick, so the audit is reproducible rather than trust-based. (d) Publish the Merkle root **before** the earliest lock in the batch, anchored via OpenTimestamps + a public post; the batch builder refuses any market with `lock_ts < now() + 10m`. (e) Never claim "beat the close" on a prediction with `uses_market_features = TRUE`.

### R3 — Point-in-time leakage makes the backtest look excellent and live results flat
The known leak vectors are already enumerated and each one is subtle: nflfastR `vegas_wp`/`vegas_wpa` are line-derived; `spread_line`/`total_line` are carried *inside* the PBP files; ESPN's injuries endpoint is a **current snapshot** with no history (retroactively reconstructing NBA/NHL who-was-out is impossible after the fact); MoneyPuck season-summary CSVs are current-season aggregates that leak the future into every past game; tennis `Max`/`Avg` are cross-book aggregates of unknown timing; nflverse `games.csv` carries 2026 lines today.
**Mitigation:** (a) `AsOfStore` — adapters cannot open a DB connection; every read is clamped to `observed_at <= feature_asof` at the query layer. (b) `banned_feature_columns` per adapter, CI-enforced against emitted feature keys. (c) **Start daily injury/availability snapshotting on day 1 for NBA, NHL and NFL** — this data is unrecoverable if not captured, and it is the single hardest part of an honest backtest. (d) One full held-out season, untouched until go/no-go. (e) Mandatory 30-day live shadow period per sport (predictions committed, graded, not promoted) before any paid-tier claim.

### R4 — Entity resolution silently corrupts the joins
Concrete, already-observed failures: 63% of UFC odds rows and 100% of 2026+ rows have no `fight_url`; `ufc_fight_results.csv` EVENT strings carry trailing whitespace; the tennis-data WTA URL pattern returns byte-identical **men's** files for 2001-2006 with no 404; ESPN uses its own athlete IDs vs tennis-data's `"Surname I."`; NFL franchise moves (OAK→LV, SD→LAC, STL→LA); EPL club-name drift; ESPN scoreboard dates are UTC-keyed so US-evening slates land on the next day.
**Mitigation:** (a) `entity_alias` with `valid_from`/`valid_to` and `confidence`; deterministic-ID match first, exact-normalized-name second, fuzzy third. (b) `resolve_entity` returning `None` writes to a **manual review queue** — the engine never drops a row silently. (c) **Join-rate SLO per sport per ingest run; the run fails and pages below 98%.** (d) Content validation on every download: magic bytes, content-type, byte-size delta vs last successful pull, and a per-source row-count floor. This catches the 504-HTML-saved-as-xlsx and the WTA-returns-ATP class of bug automatically. (e) Row-level `source_id` + `raw_ref` on everything so any bad join is traceable and reversible.

### R5 — The free archives are frozen, dying, or legally unusable
sportsbookreviewsonline.com is **entirely dead** (root 404) — the NBA and NHL closing-line history now exists only as third-party GitHub mirrors and scraped HTML with no live upstream. DillonKoch is frozen at 2021-22. `pwu97/bettingtools` (MLB 2014-2019) is dead since 2020 with license **NOASSERTION**. Jeff Sackmann's tennis repos are 404. fastRhockey/hockeyR mirrors stop at 2023-24. The Kaggle UFC set is one person's cron. MoneyPuck actively redirects scrapers to a data-licence page.
**Mitigation:** (a) **Day-1 mirror of every archive into our own object store with SHA-256 manifests**, plus a weekly checksum diff that alerts when an upstream goes dark or changes. Treat all of these as one-time loads, never as live dependencies. (b) `source.commercial_ok` gates the paid product: `bettingtools` and MoneyPuck are quarantined to backtest/dev; if legal review doesn't clear `bettingtools`, we drop MLB 2014-2019 and ship MLB on 2024+ own-capture only rather than ship unlicensed data to paying customers. (c) Because the archives cannot be replaced, **our own capture becomes the moat** — after one NFL season we will hold a closing-line archive that nobody can download for free, which is a stronger asset than anything we backfilled. Fund the cron infrastructure before funding model complexity. (d) For every frozen source, a documented "what replaces this if it's gone tomorrow" line in the adapter docstring.

---

## 7. Critical path to 2026-09-10

| Week of | Must ship |
|---|---|
| Aug 3 | **NFL ESPN odds snapshot cron live** (unrecoverable if late) + daily NBA/NHL/NFL injury snapshot cron + raw object store + `source`/`odds_snapshot` tables |
| Aug 10 | Schema deployed; NFL + EPL adapters; all archive mirrors pulled and checksummed |
| Aug 17 | NBA + NHL adapters; SBR/DillonKoch parsers (positional, gotchas handled); settlement engine |
| Aug 24 | Elo/DC baselines trained; rolling-origin backtest harness; calibration + reliability reporting |
| Aug 31 | Commitment pipeline end-to-end (Merkle + OTS anchor); public track-record page with grading-basis badges; MLB/UFC/Tennis adapters at calibrating |
| Sep 7 | Preseason dry-run: full commit→lock→capture→settle→grade loop on NFL Week 1 preseason + EPL matchday; go/no-go |
| Sep 10 | **NFL Week 1 — Live** |

F1 and Cricket adapters land Q4 2026 as shadow ingest; publication decision after one season of own-captured prices.

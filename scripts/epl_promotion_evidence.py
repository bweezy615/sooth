"""Evidence for or against promoting EPL from In calibration to Live.

The charter forbids this agent from promoting anything. This script only
assembles what the decision needs, so the user makes it on numbers rather than
on a summary.

"Live" in this project means one specific thing: **the sport can be graded
against a closing line whose provenance we can defend.** It does not mean the
model wins. NFL ships Live while losing to the market, because Live is a claim
about auditability, not profitability. Conflating the two is what the whole
product exists to avoid.

So the questions are, in order:

  1. Is the closing line genuinely documented as closing by its publisher?
  2. Is coverage complete enough to grade a full season without gaps?
  3. Does the model produce calibrated probabilities on it?
  4. How does it score against that closing line, honestly?

    python scripts/epl_promotion_evidence.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.adapters.epl import EPLAdapter  # noqa: E402

K, HFA, CARRY, BASE = 20.0, 60.0, 0.80, 1500.0
EPS = 1e-12


def build() -> pd.DataFrame:
    a = EPLAdapter()
    df = a.load_seasons(2015, 2025)
    df = df[df["FTHG"].notna() & df["FTAG"].notna()].sort_values("Date").copy()

    ratings, last, rows = {}, None, []
    for _, r in df.iterrows():
        h, aw, s = str(r["HomeTeam"]), str(r["AwayTeam"]), int(r["season"])
        if last is not None and s != last:
            for t in ratings:
                ratings[t] = BASE + (ratings[t] - BASE) * CARRY
        last = s
        rh, ra = ratings.get(h, BASE), ratings.get(aw, BASE)
        diff = rh - ra + HFA
        exp = 1 / (1 + 10 ** (-diff / 400))
        hg, ag = float(r["FTHG"]), float(r["FTAG"])
        rows.append({
            "season": s, "elo_diff": diff,
            "y": 0 if hg > ag else (1 if hg == ag else 2),
            "PSCH": r.get("PSCH"), "PSCD": r.get("PSCD"), "PSCA": r.get("PSCA"),
            "AvgCH": r.get("AvgCH"), "AvgCD": r.get("AvgCD"), "AvgCA": r.get("AvgCA"),
        })
        act = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        d = K * (act - exp) * (1 + abs(hg - ag)) ** 0.5
        ratings[h], ratings[aw] = rh + d, ra - d
    return pd.DataFrame(rows)


def main() -> None:
    f = build()

    # ---- Q1/Q2: provenance and coverage -------------------------------
    print("Q1 — provenance of the closing line")
    print("  football-data.co.uk documents its C-infixed columns as CLOSING")
    print("  prices. PSCH/PSCD/PSCA = Pinnacle Closing Home/Draw/Away.")
    print("  This is the only source in the project whose closing odds are")
    print("  labelled as closing BY THE PUBLISHER. NFL required a paid")
    print("  backfill to reach the same standard.")
    print()
    print("Q2 — coverage, by season")
    cov = []
    for s, g in f.groupby("season"):
        pin = g["PSCH"].notna().sum()
        avg = g["AvgCH"].notna().sum()
        either = (g["PSCH"].notna() | g["AvgCH"].notna()).sum()
        cov.append({"season": int(s), "fixtures": len(g), "pinnacle_close": int(pin),
                    "market_avg_close": int(avg), "either": int(either),
                    "coverage": round(either / len(g), 4)})
    ct = pd.DataFrame(cov)
    print(ct.to_string(index=False))
    print(f"\n  worst season coverage: {ct['coverage'].min():.4f}")
    print(f"  any season below 100%: {(ct['coverage'] < 1.0).sum()}")

    # ---- market, de-vigged --------------------------------------------
    for c, (p, av) in {"mh": ("PSCH", "AvgCH"), "md": ("PSCD", "AvgCD"),
                       "ma": ("PSCA", "AvgCA")}.items():
        f[c] = pd.to_numeric(f[p], errors="coerce").fillna(
            pd.to_numeric(f[av], errors="coerce"))
    f = f.dropna(subset=["mh", "md", "ma"]).reset_index(drop=True)
    inv = np.c_[1 / f.mh, 1 / f.md, 1 / f.ma]
    mkt = inv / inv.sum(axis=1, keepdims=True)

    # ---- walk-forward -------------------------------------------------
    f["p0"] = f["p1"] = f["p2"] = np.nan
    for s in sorted(f.season.unique()):
        tr = f[f.season < s]
        if len(tr) < 400:
            continue
        clf = LogisticRegression(max_iter=2000).fit(tr[["elo_diff"]], tr["y"])
        f.loc[f.season == s, ["p0", "p1", "p2"]] = clf.predict_proba(
            f.loc[f.season == s, ["elo_diff"]])
    g = f.dropna(subset=["p0"]).copy()
    m = mkt[g.index.to_numpy()]
    P = g[["p0", "p1", "p2"]].to_numpy(float)
    Y = np.eye(3)[g["y"].to_numpy(int)]

    def brier(p): return float(np.mean(np.sum((p - Y) ** 2, axis=1)))
    def ll(p): return float(-np.mean(np.log(np.clip(
        p[np.arange(len(p)), g.y.to_numpy(int)], EPS, 1))))
    def acc(p): return float(np.mean(p.argmax(1) == g.y.to_numpy(int)))

    print()
    print(f"Q3/Q4 — graded against the documented close, {len(g)} fixtures "
          f"({g.season.min()}-{g.season.max()})")
    print(f"{'':<10}{'Brier':>9}{'logloss':>10}{'acc':>8}")
    print(f"{'elo':<10}{brier(P):>9.5f}{ll(P):>10.5f}{acc(P):>8.4f}")
    print(f"{'market':<10}{brier(m):>9.5f}{ll(m):>10.5f}{acc(m):>8.4f}")
    print(f"{'delta':<10}{brier(P)-brier(m):>+9.5f}  -> model "
          f"{'BEATS' if brier(P) < brier(m) else 'LOSES TO'} market")

    print()
    print("per season, model Brier vs market Brier")
    rows = []
    for s, gg in g.groupby("season"):
        idx = gg.index.to_numpy()
        pp, mm = P[[g.index.get_loc(i) for i in idx]], mkt[idx]
        yy = np.eye(3)[gg["y"].to_numpy(int)]
        rows.append({"season": int(s), "n": len(gg),
                     "model": round(float(np.mean(np.sum((pp - yy) ** 2, axis=1))), 5),
                     "market": round(float(np.mean(np.sum((mm - yy) ** 2, axis=1))), 5)})
    st = pd.DataFrame(rows)
    st["delta"] = (st["model"] - st["market"]).round(5)
    st["model_better"] = st["delta"] < 0
    print(st.to_string(index=False))
    print(f"\n  seasons where the model beat the market: "
          f"{int(st['model_better'].sum())} of {len(st)}")

    # ---- calibration ---------------------------------------------------
    print()
    print("calibration of the home-win probability, 10 buckets")
    ph, yh = P[:, 0], (g["y"].to_numpy(int) == 0).astype(float)
    edges = np.linspace(0, 1, 11)
    idx = np.clip(np.digitize(ph, edges) - 1, 0, 9)
    tot, wsum = 0.0, 0.0
    for b in range(10):
        msk = idx == b
        if not msk.any():
            continue
        pred, act, n = ph[msk].mean(), yh[msk].mean(), int(msk.sum())
        print(f"  {edges[b]:.1f}-{edges[b+1]:.1f}  n={n:>5}  "
              f"predicted {pred:.4f}  actual {act:.4f}  gap {pred-act:+.4f}")
        tot += abs(pred - act) * n
        wsum += n
    print(f"\n  expected calibration error: {tot/wsum:.5f}")
    print()
    print("DECISION IS THE USER'S. This script promotes nothing.")


if __name__ == "__main__":
    main()

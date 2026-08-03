"""Walk-forward EPL backtest against DOCUMENTED closing odds.

Three-way (1X2), so scored with multiclass Brier and log loss rather than the
two-way metrics NFL uses. Elo produces a rating difference; a multinomial
logistic fitted ONLY on prior seasons turns that into home/draw/away
probabilities, which is how the draw gets modelled rather than assumed.

STATUS: In calibration. Nothing here is published.
"""
from __future__ import annotations
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.adapters.epl import EPLAdapter, CLOSING_COLS, AVG_CLOSING_COLS

K, HFA, CARRY, BASE = 20.0, 60.0, 0.80, 1500.0

def main():
    a = EPLAdapter()
    df = a.load_seasons(2015, 2025)
    df = df[df["FTHG"].notna() & df["FTAG"].notna()].sort_values("Date").copy()

    ratings, last_season, rows = {}, None, []
    for _, r in df.iterrows():
        h, aw, s = str(r["HomeTeam"]), str(r["AwayTeam"]), int(r["season"])
        if last_season is not None and s != last_season:
            for t in ratings: ratings[t] = BASE + (ratings[t]-BASE)*CARRY
        last_season = s
        rh, ra = ratings.get(h, BASE), ratings.get(aw, BASE)
        diff = rh - ra + HFA
        exp = 1/(1+10**(-diff/400))
        hg, ag = float(r["FTHG"]), float(r["FTAG"])
        outcome = 0 if hg > ag else (1 if hg == ag else 2)   # H / D / A
        rows.append({"season": s, "elo_diff": diff, "y": outcome,
                     "PSCH": r.get("PSCH"), "PSCD": r.get("PSCD"), "PSCA": r.get("PSCA"),
                     "AvgCH": r.get("AvgCH"), "AvgCD": r.get("AvgCD"), "AvgCA": r.get("AvgCA")})
        act = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        delta = K*(act-exp)*(1+abs(hg-ag))**0.5
        ratings[h], ratings[aw] = rh+delta, ra-delta

    f = pd.DataFrame(rows)
    # de-vigged market, preferring Pinnacle close, falling back to market avg
    for c,(p,av) in {"mh":("PSCH","AvgCH"),"md":("PSCD","AvgCD"),"ma":("PSCA","AvgCA")}.items():
        f[c] = pd.to_numeric(f[p], errors="coerce").fillna(pd.to_numeric(f[av], errors="coerce"))
    f = f.dropna(subset=["mh","md","ma"])
    inv = np.c_[1/f.mh, 1/f.md, 1/f.ma]
    mkt = inv / inv.sum(axis=1, keepdims=True)

    f["p0"]=f["p1"]=f["p2"]=np.nan
    for s in sorted(f.season.unique()):
        tr, te = f[f.season < s], f.season == s
        if len(tr) < 400: continue
        clf = LogisticRegression(max_iter=2000).fit(tr[["elo_diff"]], tr["y"])
        f.loc[te, ["p0","p1","p2"]] = clf.predict_proba(f.loc[te, ["elo_diff"]])
    g = f.dropna(subset=["p0"]).copy()
    idx = g.index
    m = mkt[[f.index.get_loc(i) for i in idx]]
    P = g[["p0","p1","p2"]].to_numpy(float)
    Y = np.eye(3)[g["y"].to_numpy(int)]

    def brier(p): return float(np.mean(np.sum((p-Y)**2, axis=1)))
    def ll(p): return float(-np.mean(np.log(np.clip(p[np.arange(len(p)), g.y.to_numpy(int)],1e-12,1))))
    def acc(p): return float(np.mean(p.argmax(1)==g.y.to_numpy(int)))

    print(f"graded fixtures : {len(g)} (seasons {g.season.min()}-{g.season.max()})")
    print(f"{'':<10}{'Brier':>9}{'logloss':>10}{'acc':>8}")
    print(f"{'elo':<10}{brier(P):>9.5f}{ll(P):>10.5f}{acc(P):>8.4f}")
    print(f"{'market':<10}{brier(m):>9.5f}{ll(m):>10.5f}{acc(m):>8.4f}")
    print(f"\ndelta (elo - market) Brier: {brier(P)-brier(m):+.5f}  "
          f"-> model {'BEATS' if brier(P)<brier(m) else 'LOSES TO'} market")
    print(f"draw rate actual {np.mean(g.y==1):.4f} | model mean p(draw) {P[:,1].mean():.4f} "
          f"| market {m[:,1].mean():.4f}")

if __name__ == "__main__":
    main()

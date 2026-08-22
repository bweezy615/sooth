"""The two emails that are the product: a slate was sealed, a week was graded.

Price alerts tell you a book is out of line right now. These two tell you the
thing sooth actually exists to do happened, and they are the reason to come
back on a Wednesday and again on a Tuesday.

The seal email is the more interesting artifact. It carries the Merkle root and
the GitHub commit that anchors it, and it lands in a mailbox that stamps its
own arrival time. That is a second, independent timestamp on the same
commitment, held by a party with no stake in us and no ability to backdate —
the recipient's mail provider. We are not claiming that as cryptography; it is
simply one more place the claim exists before the games are played.

The graded email ships whether the week was good or bad, from the same workflow
step that publishes the result, for the same reason grade.yml has an assertion
step: an honest record is one nobody chooses to send.

    python -m engine.alert_lifecycle --kind seal --commit "$GITHUB_SHA"
    python -m engine.alert_lifecycle --kind graded
    python -m engine.alert_lifecycle --selfcheck
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from . import alert_token, mailer, subscribers

WATERMARK = "data/lifecycle_sent.json"
META = "data/pro/latest.meta.json"
RECORD = "site/public/data/pickengine-record.json"
REPO = "bweezy615/sooth"


# ---- watermark --------------------------------------------------------------

def load_sent(path: str = WATERMARK) -> set[str]:
    try:
        return set(json.loads(Path(path).read_text()).get("keys", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_sent(keys: set[str], path: str = WATERMARK) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"keys": sorted(keys)}, indent=1) + "\n")


# ---- content ----------------------------------------------------------------

def _when(iso: str) -> str:
    """ISO -> a human ET-ish stamp. Falls back to the raw string, never blank."""
    try:
        d = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return str(iso)
    return d.strftime("%a %b %-d, %H:%M UTC")


def seal_content(meta: dict, commit: str | None) -> tuple[str, str, str, str, str]:
    """(key, subject, headline, blurb, body_html) for a sealed slate."""
    slate = str(meta.get("slate_id", "")) or "the next slate"
    n = meta.get("game_count")
    root = str(meta.get("merkle_root", ""))
    anchor = f"https://github.com/{REPO}/commit/{commit}" if commit else \
             f"https://github.com/{REPO}/commits/main"

    body = (
        mailer.row("slate", slate) +
        mailer.row("games sealed", f"{n} — every game on the slate, no selection rule")
        + mailer.row("first kickoff", _when(meta.get("earliest_kickoff", "")))
        + mailer.row("merkle root", root, mono=True)
        + mailer.row("timestamp anchor", anchor, mono=True)
    )
    blurb = (
        f"{n} games, sealed before any of them started. The root below is now in "
        f"a public GitHub commit, so the picks existed at that time whether they "
        f"turn out right or wrong. This email is a second copy of the same claim, "
        f"stamped by your mail provider rather than by us."
    )
    return (f"seal:{slate}",
            f"Sooth: {slate} is sealed ({n} games)",
            f"{slate} is sealed.",
            blurb, body)


def live_weeks(record: dict) -> list[dict]:
    """Graded weeks that are real, newest first. Rehearsals are not results."""
    weeks = [w for w in record.get("weeks", []) if not w.get("rehearsal")]
    return sorted(weeks, key=lambda w: str(w.get("slate_id", "")), reverse=True)


def _clv_line(week: dict) -> str:
    """CLV for the week, or the honest reason there isn't one.

    Never prints 0.00 for "we didn't measure it" — that was a real defect on
    the ledger page and it would read even worse in a mailbox, where nobody can
    click through to the caveat.
    """
    cov = week.get("clv_coverage")
    mean = None
    for m in (week.get("by_model") or {}).values():
        if m.get("mean_clv") is not None:
            mean = m["mean_clv"]
            break
    if mean is None or not cov:
        return "not measurable on this slate — no qualifying pre-close reference price"
    return f"{mean:+.2f} points on {int(round(cov * 100))}% of picks"


def graded_content(record: dict) -> tuple[str, str, str, str, str] | None:
    weeks = live_weeks(record)
    if not weeks:
        return None
    w = weeks[0]
    slate = str(w.get("slate_id", ""))
    models = w.get("by_model") or {}
    lines = ""
    for name, m in sorted(models.items()):
        pct = m.get("win_pct")
        lines += mailer.row(
            name,
            f"{m.get('record', '?')}"
            + (f" · {pct:.1%}" if isinstance(pct, (int, float)) else "")
            + (f" · Brier {m['brier']:.3f}" if m.get("brier") is not None else ""))
    body = (
        mailer.row("slate", slate)
        + mailer.row("games settled", str(w.get("n_settled", "?")))
        + lines
        + mailer.row("closing-line value", _clv_line(w))
    )
    headline_bits = " / ".join(m.get("record", "?") for _, m in sorted(models.items()))
    blurb = (
        "The break-even a bettor needs at standard -110 juice is 52.38%. That "
        "number does not move because a week went well. This email is sent by "
        "the same workflow step that publishes the result, so a losing week "
        "reaches you exactly the same way a winning one does."
    )
    return (f"graded:{slate}",
            f"Sooth: {slate} graded — {headline_bits}",
            f"{slate} is graded: {headline_bits}.",
            blurb, body)


# ---- send -------------------------------------------------------------------

def build(kind: str, meta_path: str = META, record_path: str = RECORD,
          commit: str | None = None):
    if kind == "seal":
        try:
            meta = json.loads(Path(meta_path).read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if not meta.get("slate_id"):
            return None
        return seal_content(meta, commit)
    try:
        record = json.loads(Path(record_path).read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return graded_content(record)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=("seal", "graded"), default="seal")
    ap.add_argument("--commit", default=os.environ.get("GITHUB_SHA", ""))
    ap.add_argument("--meta", default=META)
    ap.add_argument("--record", default=RECORD)
    ap.add_argument("--dry-run", action="store_true",
                    help="render and print, send nothing, touch no watermark")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    if a.selfcheck:
        return _selfcheck()

    built = build(a.kind, a.meta, a.record, a.commit or None)
    if not built:
        print(f"nothing to announce for kind={a.kind}")
        return 0
    key, subject, headline, blurb, body = built

    sent = load_sent()
    if key in sent and not a.dry_run:
        print(f"already announced {key} — not re-sending")
        return 0

    if a.dry_run:
        print(subject)
        print(headline)
        print(blurb)
        print(body[:400] + " ...")
        return 0

    resend_key = os.environ.get("RESEND_API_KEY", "")
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not resend_key:
        print("RESEND_API_KEY not set — nothing sent.", file=sys.stderr)
        return 0
    try:
        alert_token._secret()
    except alert_token.NoSecret as e:
        print(str(e), file=sys.stderr)
        return 0

    people = subscribers.recipients(stripe_key, a.kind)
    print(f"{a.kind}: {len(people)} recipient(s)")
    if not people:
        # Record it anyway. A subscriber who joins next week wants next week's
        # seal, not a backlog of announcements about slates already played.
        save_sent(sent | {key})
        return 0

    cta = ("Verify the root", mailer.BASE + "/verify") if a.kind == "seal" \
        else ("Open the ledger", mailer.BASE + "/trust")
    ok = 0
    for s in people:
        unsub = alert_token.unsub_link(s.email, mailer.BASE)
        prefs = alert_token.prefs_link(s.email, mailer.BASE)
        html = mailer.shell(
            "Sooth · slate sealed" if a.kind == "seal" else "Sooth · week graded",
            headline, blurb, body, cta[0], cta[1], unsub, prefs)
        text = (headline + "\n\n" + blurb + "\n\n" + cta[0] + ": " + cta[1]
                + mailer.text_tail(unsub, prefs))
        ok += mailer.send(resend_key, s.email, subject, html, text, unsub)
    print(f"sent {ok}/{len(people)}")
    if ok:
        save_sent(sent | {key})
    return 0 if ok else 1


def _selfcheck() -> int:
    meta = {"slate_id": "2026-W01-nfl", "game_count": 16,
            "merkle_root": "ab" * 32,
            "earliest_kickoff": "2026-09-09T20:20:00+00:00"}
    key, subj, head, blurb, body = seal_content(meta, "c0ffee1")
    assert key == "seal:2026-W01-nfl"
    assert "2026-W01-nfl" in subj and "16" in subj
    assert "ab" * 32 in body, "the root must be in the email, not just linked"
    assert "commit/c0ffee1" in body, "the anchor commit is the point"
    assert "no selection rule" in body, "the position ships with the artifact"

    # no commit id still produces a usable anchor rather than a broken link
    _, _, _, _, body2 = seal_content(meta, None)
    assert "commits/main" in body2

    rec = {"weeks": [
        {"slate_id": "REPLAY-2025-W05-nfl", "rehearsal": True,
         "n_settled": 28, "by_model": {"m": {"record": "9-5"}}},
        {"slate_id": "2026-W01-nfl", "n_settled": 16, "clv_coverage": 0.5,
         "by_model": {"elo+epa-v1": {"record": "6-10", "win_pct": 0.375,
                                     "brier": 0.271, "mean_clv": -1.4}}},
    ]}
    got = graded_content(rec)
    assert got is not None
    gkey, gsubj, ghead, gblurb, gbody = got
    assert gkey == "graded:2026-W01-nfl"
    assert "REPLAY" not in gsubj, "a rehearsal is not a result and never mails"
    assert "6-10" in gsubj, "the losing record leads the subject line"
    assert "52.38%" in gblurb, "break-even ships with every record"
    assert "-1.40 points on 50%" in gbody

    # CLV that was not measured says so, and never prints as zero
    rec2 = {"weeks": [{"slate_id": "2026-W02-nfl", "n_settled": 14,
                       "clv_coverage": 0.0,
                       "by_model": {"m": {"record": "7-7", "mean_clv": None}}}]}
    _, _, _, _, b2 = graded_content(rec2)
    assert "not measurable" in b2 and "0.00" not in b2

    # rehearsals only => nothing to announce
    assert graded_content({"weeks": [{"slate_id": "R", "rehearsal": True}]}) is None
    assert graded_content({"weeks": []}) is None

    # watermark round-trip
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = str(Path(d) / "wm.json")
        assert load_sent(p) == set()
        save_sent({"seal:x"}, p)
        assert load_sent(p) == {"seal:x"}

    print("alert_lifecycle.selfcheck: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""The Sooth broadcast graphics kit — one universe, many layouts.

Everything visual that repeats across post types lives here: the palette, the
three type roles, the persistent furniture (eyebrow, date stamp, wordmark) and
the drawing primitives the card composers assemble. engine/xcards.py holds the
layouts; this file holds the language they are written in.

THE RULE THIS FILE EXISTS TO ENFORCE
------------------------------------
Every graphic should be recognisable as Sooth before the account name is read,
WITHOUT every graphic being the same template. So the kit is deliberately split:
the furniture is fixed and cheap to apply, the composition is not provided at
all. A composer that wants a table draws a table; there is no "standard card".

Fonts: Bebas Neue for display (condensed, broadcast), Helvetica Neue for prose,
Menlo for anything with digits in a column. Inter is the brand's body face but
is not installed on this machine; Helvetica Neue is the closest neutral
grotesque available offline, and swapping it is one constant.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "site", "public", "data")
CACHE = os.path.join(ROOT, "data", "cache", "art")

POSTER = os.path.expanduser("~/sooth-poster")
F_DISPLAY = os.path.join(POSTER, "assets", "fonts", "BebasNeue.ttf")
F_BODY = "/System/Library/Fonts/HelveticaNeue.ttc"
F_MONO = "/System/Library/Fonts/Menlo.ttc"
BODY_IDX = {"regular": 0, "bold": 1, "medium": 10, "light": 7, "thin": 12}

# FROZEN MARKET. The site's teal, not the reference sheet's #00D1B2 — a card
# lands in a feed and the click lands on sooth.bet, and two teals a few degrees
# apart read as an off-brand repost. One constant to change if that is wrong.
BG      = (6, 8, 10)
PANEL   = (15, 17, 20)
PANEL2  = (28, 31, 36)
STROKE  = (42, 45, 51)
INK     = (240, 245, 246)
INK2    = (174, 189, 194)
DIM     = (84, 98, 104)
BRAND   = (45, 212, 167)
LOSS    = (255, 107, 107)
PUSH    = (150, 160, 166)

CARD_W, CARD_H = 1600, 900
PAD = 84

# X renders 16:9 largest; Instagram's feed gives a 4:5 post roughly two and a
# half times the screen height of a landscape one. Same design language, two
# canvases — a card built for one and cropped for the other loses its margins.
SIZES = {"feed": (1600, 900, 84), "portrait": (1080, 1350, 64)}

# Anything that turns a fact into advice. Checked against the RENDERED caption,
# not the template, so a value substituted at runtime cannot smuggle one past.
BANNED = ("prop of the day", "pick of the day", "lock", "best bet", "we like",
          "take the", "hammer", "value play", "free play", "parlay", "bet on",
          "guaranteed", "can't lose", "sure thing")


def check_caption(cap: str) -> None:
    low = cap.lower()
    for b in BANNED:
        if b in low:
            raise SystemExit(f"refusing to queue: caption contains {b!r} — "
                             "this account states facts, it does not advise")


def load(name: str) -> dict:
    """Read one published feed. Missing or broken means 'no card', never a guess."""
    path = name if os.path.isabs(name) else os.path.join(DATA, name)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


# ---- type -------------------------------------------------------------------

def display(size: int):
    from PIL import ImageFont
    return ImageFont.truetype(F_DISPLAY, size)


def mono(size: int, bold: bool = False):
    from PIL import ImageFont
    return ImageFont.truetype(F_MONO, size, index=1 if bold else 0)


def body(size: int, weight: str = "regular"):
    from PIL import ImageFont
    return ImageFont.truetype(F_BODY, size, index=BODY_IDX.get(weight, 0))


# ---- remote art -------------------------------------------------------------

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _team_index() -> dict:
    """slug -> record, plus 'sport:ABBR' -> record.

    Feeds disagree about how a team is named: board.json says 'Buffalo Bills',
    best_lines.json says 'BUF'. Both must resolve, and a bare abbreviation is
    ambiguous across leagues (NY is Knicks, Yankees, Jets...), so the second key
    is sport-scoped.
    """
    teams = (load("team-logos.json").get("teams") or {})
    idx = dict(teams)
    for _, t in teams.items():
        if t.get("abbr") and t.get("sport"):
            idx[f"{t['sport']}:{t['abbr']}".lower()] = t
    return idx


def _ssl_ctx():
    """A CA bundle Python can actually find.

    The venv this renders in has no system trust store, so every crest and
    headshot fetch failed CERTIFICATE_VERIFY_FAILED and every card silently
    fell back to its no-logo layout — a failure that looks like a design
    choice, which is the worst kind.
    """
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def fetch(url: str) -> str | None:
    """Cache a remote image beside the repo. Returns a path, or None.

    Failing soft matters more than the logo: a card with a missing crest is a
    plainer card, a card that raises is a card that never posts.
    """
    if not url:
        return None
    os.makedirs(CACHE, exist_ok=True)
    ext = ".png" if ".png" in url.lower() else ".jpg"
    path = os.path.join(CACHE, hashlib.sha1(url.encode()).hexdigest()[:16] + ext)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sooth-cards/1"})
        with urllib.request.urlopen(req, timeout=8, context=_ssl_ctx()) as r:
            blob = r.read()
        if len(blob) < 200:
            return None
        with open(path, "wb") as fh:
            fh.write(blob)
        return path
    except Exception:
        return None


def crest(name: str, sport: str = "") -> str | None:
    idx = _team_index()
    t = idx.get(_slug(name)) or idx.get(f"{sport}:{name}".lower())
    return fetch(t.get("logo")) if t else None


def headshot(name: str) -> str | None:
    p = (load("player-headshots.json").get("players") or {}).get(_slug(name))
    return fetch(p.get("img")) if p else None


# ---- the canvas -------------------------------------------------------------

class Card:
    """A 16:9 ground with Sooth's furniture on it and nothing else decided."""

    def __init__(self, eyebrow: str, stamp: bool = True, size: str = "feed"):
        from PIL import Image, ImageDraw
        w, h, pad = SIZES.get(size, SIZES["feed"])
        self.img = Image.new("RGB", (w, h), BG)
        self.d = ImageDraw.Draw(self.img)
        self.w, self.h, self.pad = w, h, pad
        self.size = size
        # nothing a composer draws may cross this line: below it is the
        # wordmark's air. Several cards printed straight through it before the
        # rule existed.
        self.floor = h - pad - 40
        self._furniture(eyebrow, stamp)

    def _furniture(self, eyebrow: str, stamp: bool) -> None:
        p = self.pad
        wide = self.size == "feed"
        self.d.rectangle([p, p, p + (46 if wide else 36), p + 5], fill=BRAND)
        self.tracked((p + (66 if wide else 52), p - 6), eyebrow.upper(),
                     mono(23 if wide else 20, True), BRAND, 3)
        if stamp:
            s = "SOOTH // " + datetime.now(timezone.utc).strftime("%b %d").upper()
            f = mono(21 if wide else 18)
            self.tracked((self.w - p - self.track_w(s, f, 3), p - 4), s, f, DIM, 3)
        self.d.line([p, p + 42, self.w - p, p + 42], fill=STROKE, width=1)

    def wordmark(self) -> None:
        f = display(42 if self.size == "feed" else 38)
        t = "SOOTH.BET"
        w = self.track_w(t, f, 4)
        self.tracked((self.w - self.pad - w, self.h - self.pad - 34), t, f, INK, 4)

    def done(self):
        """Stamp the wordmark on top and hand back the image.

        Composers call this instead of touching .img. The wordmark used to be
        painted with the rest of the furniture, before the layout existed, so a
        table row that ran long simply drew over it.
        """
        self.wordmark()
        return self.img

    # -- primitives --

    def track_w(self, text: str, font, track: int) -> float:
        return sum(self.d.textlength(c, font=font) + track for c in text) - track

    def tracked(self, xy, text: str, font, fill, track: int = 2) -> float:
        """Letter-spaced text. PIL has no tracking, and untracked uppercase
        labels are the single loudest tell of a generated graphic."""
        x, y = xy
        for c in text:
            self.d.text((x, y), c, font=font, fill=fill)
            x += self.d.textlength(c, font=font) + track
        return x - xy[0] - track

    def label(self, xy, text: str, fill=DIM, size: int = 21) -> None:
        self.tracked(xy, text.upper(), mono(size), fill, 3)

    def panel(self, box, fill=PANEL, stroke=STROKE, r: int = 6) -> None:
        self.d.rounded_rectangle(box, radius=r, fill=fill, outline=stroke, width=1)

    def rule(self, x1, y, x2, fill=STROKE) -> None:
        self.d.line([x1, y, x2, y], fill=fill, width=1)

    def paste(self, path: str | None, box) -> bool:
        """Fit an image into a box, preserving aspect, centred. False if absent."""
        if not path:
            return False
        from PIL import Image
        try:
            src = Image.open(path).convert("RGBA")
        except Exception:
            return False
        x, y, w, h = box
        sc = min(w / src.width, h / src.height)
        src = src.resize((max(1, int(src.width * sc)), max(1, int(src.height * sc))),
                         Image.LANCZOS)
        self.img.paste(src, (int(x + (w - src.width) / 2),
                             int(y + (h - src.height) / 2)), src)
        return True

    def wrap(self, text: str, font, max_w: int) -> list[str]:
        """Wrap paragraph by paragraph. text.split() flattens blank lines into
        spaces, which runs sentences together — blank lines are structure."""
        out: list[str] = []
        for para in text.split("\n"):
            if not para.strip():
                out.append("")
                continue
            line = ""
            for word in para.split():
                trial = (line + " " + word).strip()
                if self.d.textlength(trial, font=font) <= max_w:
                    line = trial
                else:
                    if line:
                        out.append(line)
                    line = word
            if line:
                out.append(line)
        return out

    def para(self, xy, text: str, font, fill=INK2, max_w=600, lead=None,
             limit=None) -> int:
        """Draw wrapped prose, clipped to `limit`. Returns the y it ended at."""
        x, y = xy
        lead = lead or int(font.size * 1.5)
        for line in self.wrap(text, font, max_w):
            if limit and y + lead > limit:
                break
            self.d.text((x, y), line, font=font, fill=fill)
            y += lead
        return y

    def hbar(self, x, y, w, h, frac: float, fill, back=PANEL2, rtl=False) -> None:
        """A proportion bar. rtl grows leftward, for the away column of a
        head-to-head where the two sides must read as mirrored."""
        frac = max(0.0, min(1.0, frac))
        self.d.rectangle([x, y, x + w, y + h], fill=back)
        if frac <= 0:
            return
        run = max(2, int(w * frac))
        self.d.rectangle([x + w - run, y, x + w, y + h] if rtl
                         else [x, y, x + run, y + h], fill=fill)

    def sparkline(self, box, values, colour=BRAND, fill_under=True,
                  dot_last=True) -> None:
        """A price series. Flat and empty series are drawn, not skipped — a
        market that did not move is a fact the card is allowed to state."""
        x, y, w, h = box
        vals = [v for v in values if isinstance(v, (int, float))]
        if len(vals) < 2:
            return
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        pts = [(x + w * i / (len(vals) - 1), y + h - (v - lo) / span * h)
               for i, v in enumerate(vals)]
        for gy in range(1, 4):                       # the faint terminal grid
            yy = y + h * gy / 4
            self.d.line([x, yy, x + w, yy], fill=(20, 23, 27), width=1)
        if fill_under:
            self.d.polygon(pts + [(x + w, y + h), (x, y + h)], fill=(12, 34, 30))
        self.d.line(pts, fill=colour, width=4, joint="curve")
        if dot_last:
            ex, ey = pts[-1]
            self.d.ellipse([ex - 9, ey - 9, ex + 9, ey + 9], fill=BG,
                           outline=colour, width=4)

    def figure(self, xy, text: str, size: int, fill=BRAND, font=None):
        """A headline number. Bebas has tight side bearings; this returns the
        drawn width so composers can sit a unit or a delta beside it."""
        f = font or display(size)
        self.d.text(xy, text, font=f, fill=fill)
        return self.d.textlength(text, font=f)

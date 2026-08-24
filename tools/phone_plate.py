"""Cut the phone's masthead plate out of the desktop hero render.

    python3 tools/phone_plate.py

Why a derived crop and not the hero itself
-----------------------------------------
The phone home is the most-visited surface on the site and the one where
bandwidth actually costs the visitor something. assets/hero.jpg is 2000px and
about 150KB, and the landing page deliberately arranges for a phone to request
it ZERO times — the hero is display:none below 860px and the URL is behind a
min-width media query. Reaching for that same file to decorate the app shell
would hand all of that back for a decorative band.

So the phone gets its own asset, cut from the same render so it is literally
the same object in the same room, at a size a phone can justify: about a fifth
of the pixels and a fifth of the bytes.

Why a crop and not a second render
----------------------------------
A masthead band 120px tall on a 390px screen is small enough that a dedicated
camera would be invisible effort — nobody can tell a fresh render from a crop
at that size, and a crop costs seconds instead of ten minutes of CPU. The seal
view in tools/render_hero.py is a real second camera because /picks shows it
large; this does not.

Outputs
-------
`site/public/assets/env-phone.jpg` — 900x506, the room plate every page sits
in, at a size a phone should pay for. Same reasoning as below: desk.css serves
the 1920px env.jpg only above 860px.

`site/public/assets/hero-phone.jpg` — 900x430, which covers a 390pt-wide band
at just over 2x. Not 3x: at this size, in a band that is mostly dark room
behind a scrim, the third pixel is bytes nobody sees.
"""

import os

from PIL import Image

SRC = "site/public/assets/hero.jpg"
OUT = "site/public/assets/hero-phone.jpg"

OUT_W, OUT_H = 900, 430

# The region of the 2000x920 hero to keep, in source pixels.
#
# Chosen so the block is fully inside the frame with its base and the shards
# included — the shards are what stop the bottom edge reading as a cut — and so
# a wide stretch of dark floor survives on the left. That left area is not
# spare: the wordmark sits on it, and if the crop tightened onto the block the
# phone header would be white type on lit ice.
CROP = (560, 150, 2000, 838)          # left, top, right, bottom -> 1440x688


# The room plate, for phones. No crop — env.jpg is already composed to be
# filled with `cover` at any aspect, so the phone wants the same picture at a
# size a phone should pay for, not a different framing of it.
ENV_SRC = "site/public/assets/env.jpg"
ENV_OUT = "site/public/assets/env-phone.jpg"
ENV_W, ENV_H = 900, 506


def env_plate():
    """UNUSED SINCE 2026-08-23. desk.css no longer mounts a room behind pages —
    see the REMOVED block in that file for why three attempts failed. Kept
    because tools/render_hero.py still has an `env` view and this is what
    downsizes it; nothing on the site loads either file today."""
    if not os.path.exists(ENV_SRC):
        print("skip: " + ENV_SRC + " not rendered yet (SOOTH_HERO_VIEW=env)")
        return
    im = Image.open(ENV_SRC).convert("RGB").resize((ENV_W, ENV_H), Image.LANCZOS)
    im.save(ENV_OUT, "JPEG", quality=76, optimize=True, progressive=True)
    print("WROTE %s  %dx%d  %.0fKB"
          % (ENV_OUT, ENV_W, ENV_H, os.path.getsize(ENV_OUT) / 1024.0))


def main():
    if not os.path.exists(SRC):
        raise SystemExit(
            SRC + " is missing — render the hero first:\n"
            "  /Applications/Blender.app/Contents/MacOS/Blender --background "
            "--factory-startup --python tools/render_hero.py")

    im = Image.open(SRC).convert("RGB")
    w, h = im.size
    if (w, h) != (2000, 920):
        # Not fatal, but the CROP box above is expressed in source pixels and
        # would silently frame something else.
        print("WARNING: expected a 2000x920 hero, got %dx%d — "
              "CROP is in source pixels and may now frame the wrong region"
              % (w, h))

    im = im.crop(CROP).resize((OUT_W, OUT_H), Image.LANCZOS)
    im.save(OUT, "JPEG", quality=78, optimize=True, progressive=True)
    print("WROTE %s  %dx%d  %.0fKB"
          % (OUT, OUT_W, OUT_H, os.path.getsize(OUT) / 1024.0))
    env_plate()


main()

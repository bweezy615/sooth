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

Output
------
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


main()

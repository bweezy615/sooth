"""The offline shell must not outlive the shell it is a copy of.

site/public/sw.js caches the app shell under a cache name. Everything served
is network-first, so an online visitor always gets fresh files - but the name
is what decides whether an OFFLINE visitor, and any browser serving from the
cache while the network is slow, keeps yesterday's design.

That name used to be a hand-typed counter ('sooth-v23') with a comment asking
whoever edits desk.js or desk.css to bump it. On 2026-08-28 desk.js was
changed twice in one session - the sport rail, then a shared sportLabel() -
and the counter was not touched either time. Nobody was checking, and nothing
would have gone wrong loudly.

So the name is now derived from the shell's own bytes, and this test is the
thing that notices.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SW = ROOT / "site/public/sw.js"
SHELL = ("site/public/assets/desk.js", "site/public/assets/desk.css")


def shell_fingerprint() -> str:
    h = hashlib.sha256()
    for rel in SHELL:
        # ponytail: read_text folds CRLF to LF, so a Windows checkout and CI
        # fingerprint the same shell to the same name.
        h.update((ROOT / rel).read_text(encoding="utf-8").encode("utf-8"))
    return h.hexdigest()[:12]


def test_the_cache_name_matches_the_shell_it_holds():
    declared = re.search(r"const CACHE = '([^']+)'", SW.read_text(encoding="utf-8"))
    assert declared, "sw.js no longer declares CACHE - update this test"
    want = f"sooth-{shell_fingerprint()}"
    assert declared.group(1) == want, (
        f"desk.js or desk.css changed but sw.js still names its cache "
        f"'{declared.group(1)}'. A returning visitor would keep the previous "
        f"shell offline. Set it to: const CACHE = '{want}';"
    )


def test_the_worker_is_network_first():
    """Cache-first would put a price board's numbers behind a cached copy.

    The whole site is a price board, so this is a correctness property, not a
    performance preference: the network wins and the cache only answers when
    the network cannot.
    """
    src = SW.read_text(encoding="utf-8")
    handler = src[src.index("addEventListener('fetch'"):]
    fetch_at = handler.index("fetch(e.request)")
    match_at = handler.index("caches.match(")
    assert fetch_at < match_at, (
        "sw.js consults its cache before the network - a stale board would be "
        "served to an online visitor"
    )

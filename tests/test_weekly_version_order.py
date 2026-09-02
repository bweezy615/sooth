"""v10 must beat v2, not lose to it alphabetically.

weekly.py publishes the un-versioned commitment/reveal pair that /verify tells
readers to curl. It used to pick that pair with `sorted(glob(...))[-1]`, which
is lexicographic: "...v9.json" sorts after "...v10.json", so the tenth seal of
a slate would have published the ninth. A reader following /verify would then
compute a root that disagrees with /ledger and conclude they had caught us
tampering. Latent until a slate reaches v10 - this is the alarm.
"""
from pathlib import Path

from engine.pipeline.weekly import _newest_version


def _touch(d: Path, versions, kind="commitment"):
    for v in versions:
        (d / f"2026-W01-nfl.{kind}.v{v}.json").write_text("{}")
    return d.glob(f"2026-W01-nfl.{kind}.v*.json")


def test_double_digit_versions_beat_single_digit(tmp_path):
    picked = _newest_version(_touch(tmp_path, [1, 2, 9, 10]))
    assert picked.name.endswith("v10.json"), (
        f"picked {picked.name}; lexicographic sort would pick v9")


def test_still_right_below_ten(tmp_path):
    assert _newest_version(_touch(tmp_path, [1, 2, 4])).name.endswith("v4.json")


def test_no_versions_is_none(tmp_path):
    assert _newest_version(tmp_path.glob("nothing.v*.json")) is None

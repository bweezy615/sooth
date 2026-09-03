"""_load_slate must distinguish "cannot attempt" from "the blob is wrong".

capture.yml scopes PRO_PAYLOAD_KEY to the engine.lines step, so the
best_lines step runs with no key on every production run. That has to stay
quiet. What must NOT stay quiet is a key that IS present and still fails to
decrypt: that is a wrong key or a tampered pro payload, and until 2026-09-03
a bare `except Exception` swallowed it into the same silent fallback.
"""
import json

import pytest

from engine.best_lines import _load_slate

SLATE = "2026-W01-nfl"
PUBLIC_GAMES = [{"game_id": "g1", "home": "CIN", "away": "TB",
                 "independent": {"pick": "CIN", "prob": 0.57}}]


def _tree(tmp_path, blob: str):
    """A minimal repo shape: _load_slate walks data_dir.parents[2] for data/pro."""
    data = tmp_path / "site" / "public" / "data"
    data.mkdir(parents=True)
    (data / "slates.json").write_text(json.dumps({"latest": SLATE}))
    (data / f"{SLATE}.json").write_text(json.dumps({"games": PUBLIC_GAMES}))
    pro = tmp_path / "data" / "pro"
    pro.mkdir(parents=True)
    (pro / f"{SLATE}.pro.enc").write_text(blob)
    return data


def test_no_key_falls_back_to_the_public_file_quietly(tmp_path, monkeypatch):
    monkeypatch.delenv("PRO_PAYLOAD_KEY", raising=False)
    # load_key also reads a repo-root .env; point it at an empty tree.
    monkeypatch.chdir(tmp_path)
    data = _tree(tmp_path, "not-even-base64")
    slate_id, games = _load_slate(data)
    assert slate_id == SLATE
    assert games == PUBLIC_GAMES, "no key must degrade to the public slate"


def test_a_present_key_that_cannot_decrypt_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("PRO_PAYLOAD_KEY", "ab" * 32)
    from engine import prosec
    # Valid ciphertext under a DIFFERENT key: the wrong-key / tampered case.
    blob = prosec.encrypt(json.dumps({"games": []}), key=bytes.fromhex("cd" * 32))
    data = _tree(tmp_path, blob)
    with pytest.raises(Exception) as exc:
        _load_slate(data)
    assert not isinstance(exc.value, (ImportError, RuntimeError)), (
        "a bad blob must not be reported as a missing key")

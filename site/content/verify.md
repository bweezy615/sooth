---
title: "How to verify our prediction record yourself"
description: "A plain-English guide to checking that our published record is complete and unedited, using a 30-line script that does not trust any of our code."
last_updated: 2026-08-02
---

# How to verify our record

Every sports prediction site says it publishes its results. Almost none of them
publish results you can check. The record is stored on their server, it is
editable, and a losing pick can quietly disappear between the day it was made
and the day you look at it.

This page shows you how to prove, for yourself, that our record has not been
edited. You do not have to trust us, and you do not have to run our software.
The whole check is about thirty lines of code that you can read in a minute.

You do need to be comfortable copying a command into a terminal. You do not need
to be a programmer.

---

## The idea, in plain English

Imagine that before every NFL Sunday we write our predictions on a sheet of
paper, seal it in an envelope, and post the envelope to ourselves. Then, after
the games, we open it in public. If the postmark is from Friday, we could not
have changed anything after the games.

A **cryptographic hash** is the digital version of that sealed envelope. It is a
one-way fingerprint: you feed in any text, and you get back a 64-character
string. Change a single character of the text - a probability from 0.66 to 0.67,
a team name, a timestamp - and the fingerprint changes completely and
unpredictably. You cannot work backwards from the fingerprint to the text, and
you cannot construct different text that produces the same fingerprint.

So before the first kickoff of every slate we publish one fingerprint. It gives
nothing away: it is 64 characters of noise, and no one can read our picks out of
it. After the games finish we publish the predictions themselves. Anyone can
then re-run the fingerprint on the published predictions and check it matches
the one we published on Friday.

If it matches, the record is exactly what we committed to before kickoff. If we
had deleted a loss, added a win, changed a probability, or even reordered the
list, the fingerprint would not match and you would catch us.

### Why a "Merkle tree" rather than one big fingerprint

We could hash the whole slate as one blob. Instead we hash each prediction
individually, then hash those hashes together in pairs, then hash those results
in pairs, and so on up to a single fingerprint at the top. That top fingerprint
is called the **Merkle root**.

The tree structure buys one useful property: we can prove that a single
prediction was part of the committed slate without revealing the other
predictions. That short list of hashes is called an **inclusion proof**. It
matters for subscriber-only predictions, where we want to prove a pick was
committed before kickoff without publishing it to everyone.

### The timestamp

A fingerprint published before kickoff only means something if you can tell it
was published before kickoff. We commit the root to a public Git repository, so
the timestamp comes from GitHub, not from us. We cannot back-date a GitHub
commit that is already public, and you can look at the commit history yourself.

---

## What we publish for every slate

Two files, both plain JSON.

**`/data/<slate-id>.commitment.json`** goes up before the first kickoff. It
contains only the root fingerprint and the counts. For NFL Week 1 of 2026 it
reads:

```json
{
  "algorithm": "sha256-merkle-v1",
  "committed_at": "2026-08-03T02:50:37.265208+00:00",
  "earliest_kickoff": "2026-09-09T20:20:00+00:00",
  "merkle_root": "d081c00f901874be7a1d868f0f6f77d3b76125643a1416d8463b10ede33d7f7a",
  "n_predictions": 16,
  "slate_id": "2026-W01-nfl",
  "sport": "nfl"
}
```

Note that `committed_at` is over a month before `earliest_kickoff`. Note also
that this file tells you nothing about who we picked. That is the point.

**`/data/<slate-id>.reveal.json`** is published alongside the commitment. It
contains the same root, every prediction in full, and the individual leaf
fingerprints — so the check below works before kickoff, not only after.
Grading is added once the games settle.

Both files are also in the public code repository under `data/ledger/`.

---

## The check, step by step

### Step 1: get the two files

```
curl -O https://sooth.bet/data/2026-W01-nfl.commitment.json
curl -O https://sooth.bet/data/2026-W01-nfl.reveal.json
```

### Step 2: save this script as `verify.py`

It uses nothing but Python's standard library, which means there is nothing to
install and no package of ours anywhere in the process. Read it before you run
it - that is the point of it being short.

```python
# verify.py - independently check a committed slate.
# Standard library only. No dependency on the publisher's code.
import hashlib, json, sys

def sha(prefix, *parts):
    h = hashlib.sha256()
    h.update(prefix)
    for p in parts:
        h.update(p)
    return h.hexdigest()

def canonical(obj):
    # Deterministic JSON: keys sorted, no extra whitespace.
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def leaf(prediction):
    return sha(b"\x00", canonical(prediction))

def pair(left, right):
    return sha(b"\x01", bytes.fromhex(left), bytes.fromhex(right))

def root(leaves):
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])   # duplicate the odd one out
        level = [pair(level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]

commitment = json.load(open(sys.argv[1]))
reveal     = json.load(open(sys.argv[2]))

leaves = [leaf(p) for p in reveal["predictions"]]

print("predictions revealed :", len(reveal["predictions"]))
print("predictions committed:", commitment["n_predictions"])
print("committed at         :", commitment["committed_at"])
print("earliest kickoff     :", commitment["earliest_kickoff"])
print()
print("published root       :", commitment["merkle_root"])
print("recomputed root      :", root(leaves))
print()

ok = (len(reveal["predictions"]) == commitment["n_predictions"]
      and leaves == reveal["leaves"]
      and root(leaves) == commitment["merkle_root"])
print("VERIFIED" if ok else "MISMATCH - the record does not match the commitment")
```

### Step 3: run it

```
python3 verify.py 2026-W01-nfl.commitment.json 2026-W01-nfl.reveal.json
```

Output for NFL Week 1 of 2026:

```
predictions revealed : 16
predictions committed: 16
committed at         : 2026-08-03T02:50:37.265208+00:00
earliest kickoff     : 2026-09-09T20:20:00+00:00

published root       : d081c00f901874be7a1d868f0f6f77d3b76125643a1416d8463b10ede33d7f7a
recomputed root      : d081c00f901874be7a1d868f0f6f77d3b76125643a1416d8463b10ede33d7f7a

VERIFIED
```

The two roots match, so the sixteen predictions in the reveal file are exactly
the sixteen we sealed on 3 August 2026, five weeks before kickoff.

### Step 4: prove to yourself that it would catch us

Do not take our word for the fact that the check is sensitive. Break something
and watch it fail. Open the reveal file in a text editor, find any prediction,
change its `probability` from `0.6615` to `0.99`, save, and run the script
again. The recomputed root becomes a completely different string
(`13a070aa9e...` in our test) and the script prints `MISMATCH`.

That is the entire security argument. One digit in one of sixteen predictions
is enough to break the match. There is no way for us to quietly improve the
record after the fact.

---

## Checking a single prediction: inclusion proofs

Sometimes you only want to check one pick, and sometimes we only publish one
pick - for example a subscriber-only prediction where the rest of the slate is
not public. An inclusion proof handles that case.

The proof is a short list of sibling fingerprints, one for each level of the
tree. You start with the fingerprint of your prediction, combine it with the
first sibling, combine that result with the second sibling, and keep going. If
you end up at the published root, your prediction was definitely in the
committed slate.

For a 16-prediction slate the proof is four hashes long. Sixteen becomes eight,
eight becomes four, four becomes two, two becomes one.

### Worked example

The first prediction in the Week 1 slate, in canonical form, is this exact
string of 281 characters:

```
{"created_at":"2026-09-09T20:20:00+00:00","event_id":"2026_01_NE_SEA","line":null,"market":"moneyline","model_version":"elo-mov-v1+iso","probability":0.6615,"rationale":"elo 1692 vs 1604, rest diff +0","reference_line":3.5,"reference_price":-198,"selection":"side_a","sport":"nfl"}
```

Its leaf fingerprint is:

```
2ee7fb4740fafe6bbadab1e45bd2f3e9ce0578ced2f1628a82cba5d4b8b2f5bc
```

And its inclusion proof, four steps, is:

```json
[
  {"side": "right", "hash": "4d433651a9f54a1fdf0ee279a08911cd66ad0b1f35dcf309eb45e68af3beccaa"},
  {"side": "right", "hash": "259bd611b859eb91d815444c743cf6129d0e122116e79285f18f5a8f7b79c2c8"},
  {"side": "right", "hash": "27c786e1d14b4dd9c47b0f5bee0d4d685c1cfb7e9a886299d4a2c9d6e40c26ad"},
  {"side": "right", "hash": "9a0355b99163949c25926e550389102e8c5786d9c0aa987885a2fb33c11d369b"}
]
```

`"side": "right"` means the sibling goes on the right of your running value;
`"left"` means it goes on the left. Order matters, which is why we record it.

Add this to the script above and run it to confirm:

```python
def check_proof(leaf_hash, proof, expected_root):
    node = leaf_hash
    for step in proof:
        if step["side"] == "right":
            node = pair(node, step["hash"])
        else:
            node = pair(step["hash"], node)
    return node == expected_root
```

Feed it the leaf, the four proof steps, and the published root
`d081c00f90...`, and it returns `True`.

---

## The technical specification, for anyone writing their own checker

You do not have to use Python. Any language with SHA-256 will do. The rules are:

1. **Canonical JSON.** Serialise each prediction with keys sorted in ascending
   byte order, no whitespace between tokens, UTF-8 encoding. Numbers appear
   exactly as they do in the published file.
2. **Leaf hash.** `SHA-256(0x00 || canonical_json_bytes)`, output as lowercase
   hexadecimal.
3. **Internal node.** `SHA-256(0x01 || left_32_bytes || right_32_bytes)`, where
   the two child hashes are decoded from hex to raw bytes before being
   concatenated.
4. **Odd levels.** If a level of the tree has an odd number of nodes, duplicate
   the last node so it pairs with itself.
5. **Order.** Predictions are hashed in the order they appear in the reveal
   file. Reordering changes the root.
6. **Identifier.** Every commitment file records `"algorithm":
   "sha256-merkle-v1"`. If we ever change any of the rules above, the identifier
   changes with them, and old slates remain verifiable under the old rules.

The distinct `0x00` and `0x01` prefixes on leaves and internal nodes are
deliberate. Without them, an internal node could be presented as though it were
a leaf, which is a known weakness in naively built Merkle trees.

---

## What this proves, and what it does not

**It proves** that the predictions you are reading are the complete, unaltered
set we committed to before the first kickoff of that slate, and that we
committed to them at the time the public Git history says we did.

**It does not prove** that the predictions are any good. Cryptography cannot
make a forecast accurate. Our own backtest says our model does not beat the
closing market - the numbers are on the [methodology page](/methodology),
including the ones that make us look bad.

Verification makes our reporting honest. It does not make our model right.
Those are separate things, and conflating them is one of the more common tricks
in this industry.

---

## If a check ever fails

Tell us, publicly, and tell anyone else you like. A failed verification on a
published slate would mean either a bug in our pipeline or that we tampered with
the record. Both are things you are entitled to know about, and a system that
only works when nobody checks is not worth building.

---

*We publish predictions for analysis and entertainment. We do not accept wagers.
See [/disclaimers](/disclaimers).*

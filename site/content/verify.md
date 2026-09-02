---
title: "How to verify our prediction record yourself"
description: "A plain-English guide to checking that our published record is complete and unedited, using a 30-line script that does not trust any of our code."
last_updated: 2026-09-01
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
matters whenever one prediction travels on its own — quoted in a post, or sent
in an alert email — and you want to test that single claim without fetching and
re-hashing the whole slate.

### The timestamp

A fingerprint published before kickoff only means something if you can tell it
was published before kickoff. We commit the root to a public Git repository, so
the timestamp comes from GitHub, not from us. We cannot back-date a GitHub
commit that is already public, and you can look at the commit history yourself.

---

## What we publish for every slate

Two files, both plain JSON.

**`/data/<slate-id>.commitment.json`** goes up before the first kickoff. It
contains only the root fingerprint and the counts. For the slate below,
{{fig:slate.id}}, it reads:

``` {.json .frosted}
{{fig:slate.commitment_json}}
```

Note that `committed_at` is {{fig:slate.days_before_kickoff}} days before
`earliest_kickoff`. Note also that this file tells you nothing about who we
picked. That is the point.

**`/data/<slate-id>.reveal.json`** is published alongside the commitment. It
contains the same root, every prediction in full, and the individual leaf
fingerprints — so the check below works before kickoff, not only after.
Grading is added once the games settle.

Both files are also in the public code repository under `data/ledger/`.

---

## The check, step by step

### Step 1: get the two files

```
curl -O https://sooth.bet/data/{{fig:slate.id}}.commitment.json
curl -O https://sooth.bet/data/{{fig:slate.id}}.reveal.json
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
python3 verify.py {{fig:slate.id}}.commitment.json {{fig:slate.id}}.reveal.json
```

Output for {{fig:slate.id}}:

``` {.frosted}
{{fig:slate.sample_output}}
```

The two roots match, so the {{fig:slate.n_predictions}} predictions in the reveal
file are exactly the {{fig:slate.n_predictions}} we sealed on
{{fig:slate.sealed_human}}, {{fig:slate.days_before_kickoff}} days before the
first kickoff. The
`version`/`supersedes` fields chain this seal to the earlier ones on the
ledger; re-sealing before kickoff is allowed, silent editing is not.

### Step 4: prove to yourself that it would catch us

Do not take our word for the fact that the check is sensitive. Break something
and watch it fail. Open the reveal file in a text editor, find the **first**
prediction, change its `probability` from `{{fig:slate.first_probability}}` to
`0.99`, save, and run the script again. The recomputed root becomes a completely
different string (`{{fig:slate.tampered_root_abbrev}}` when we do it) and the
script prints `MISMATCH`.

That is the entire security argument. One digit in one of
{{fig:slate.n_predictions}} predictions is enough to break the match. There is no way for us to quietly improve the
record after the fact.

---

## Checking a single prediction: inclusion proofs

Sometimes you only want to check one pick — one prediction quoted in a post,
or carried in an alert email, away from the slate it came from. An inclusion
proof handles that case.

The proof is a short list of sibling fingerprints, one for each level of the
tree. You start with the fingerprint of your prediction, combine it with the
first sibling, combine that result with the second sibling, and keep going. If
you end up at the published root, your prediction was definitely in the
committed slate.

This slate holds {{fig:slate.n_predictions}} predictions, so its proofs are
{{fig:slate.proof_len}} hashes long: {{fig:slate.proof_shrink}}.

### Worked example

The first prediction in the {{fig:slate.id}} slate, in canonical form, is this
exact string of {{fig:slate.first_canonical_len}} characters:

``` {.frosted}
{{fig:slate.first_canonical}}
```

Its leaf fingerprint is:

``` {.frosted}
{{fig:slate.first_leaf}}
```

And its inclusion proof, {{fig:slate.proof_len}} steps, is:

``` {.json .frosted}
{{fig:slate.proof_json}}
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

Feed it the leaf, the {{fig:slate.proof_len}} proof steps, and the published
root `{{fig:slate.root_abbrev}}`, and it returns `True`.

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

"""A workflow that pays for odds must not report green when it got none.

`docs/plans/scheduled-runs-and-silent-green.md` swept every use of
`continue-on-error` on 2026-08-28 and set the rule: *the last meaningful step
in a job must be able to fail it. A guard is for a step whose failure the rest
of the job can survive, never for all of them.* It ruled `capture.yml` "fine,
deliberately" on the grounds that its two unguarded ESPN steps make a total
failure red.

The 401 outage that began 2026-09-07 06:36 UTC was not a total failure, and
that is exactly the gap. The Odds API rejected every call for days while ESPN
kept answering, so `capture-odds` reported green every thirty minutes with
`board.json` frozen at 2026-09-07T06:34Z straight through NFL week 1. Nothing
in the Actions tab could show it; you had to read the file's own
`generated_at`, which is how the outage was eventually found
(`docs/plans/2026-09-07-odds-api-key-401.md`).

So the rule needs a test, not just a doc. A step that spends Odds API credits
and swallows its own failure must be named by a later step that can redden the
run — or be listed below with the reason it is exempt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"

# Steps that spend credits, swallow failure, and are deliberately NOT allowed
# to redden their run. Each needs a reason, and the reason has to be about what
# else in that job would go red instead.
EXEMPT = {
    # scheduled-runs-and-silent-green.md: "edges.yml keeps the guard on
    # middles, because a transient Odds API failure must not cost the moves
    # rebuild; it is the zero-credit step, which reads only committed capture
    # and has no legitimate reason to fail, that is now allowed to redden the
    # run." middles.json can therefore freeze quietly — a known, accepted cost,
    # unlike capture.yml's board, which had no such second deliverable.
    ("edges.yml", "Refresh middles/arbs"),
}


def _steps(text: str) -> list[str]:
    """Split a job's YAML into per-step chunks.

    Text, not a YAML parse: pyyaml is not a declared dependency of this repo
    and tests/test_workflows_regenerate.py reads workflows the same way.
    """
    parts = re.split(r"\n(?=      - (?:name|uses):)", text)
    return parts[1:] if len(parts) > 1 else []


def _name(step: str) -> str:
    m = re.search(r"- name:\s*(.+)", step)
    return m.group(1).strip() if m else "<unnamed>"


def _exempt(wf: str, name: str) -> bool:
    return any(wf == f and name.startswith(p) for f, p in EXEMPT)


@pytest.mark.parametrize("wf", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_a_credit_spending_step_that_swallows_failure_can_still_redden_the_run(wf):
    text = wf.read_text(encoding="utf-8")
    for step in _steps(text):
        if "ODDS_API_KEY" not in step:
            continue
        if not re.search(r"^\s*continue-on-error:\s*true", step, re.M):
            continue  # its failure already fails the job

        name = _name(step)
        if _exempt(wf.name, name):
            continue

        sid = re.search(r"^\s*id:\s*(\S+)", step, re.M)
        assert sid, (
            f"{wf.name}: step {name!r} spends Odds API credits and carries "
            f"continue-on-error, but has no `id`, so nothing can reference its "
            f"outcome. Give it an id and add a guard step, or add it to EXEMPT "
            f"with the reason another step in the job goes red instead."
        )
        marker = f"steps.{sid.group(1)}.outcome"
        assert marker in text, (
            f"{wf.name}: step {name!r} pays for odds and swallows its own "
            f"failure, and no later step checks `{marker}`. This workflow will "
            f"report success while its published data freezes — the defect "
            f"that hid the 2026-09-07 Odds API outage for two and a half days. "
            f"Add a final step: if: always() && {marker} == 'failure'."
        )


def test_the_board_refresh_is_the_case_this_file_exists_for():
    """capture.yml specifically, since it is the one that went stale."""
    text = (WORKFLOWS / "capture.yml").read_text(encoding="utf-8")
    assert "id: board" in text
    assert "steps.board.outcome == 'failure'" in text, (
        "board.json is published by engine.lines alone; if that step can fail "
        "silently the live board freezes with the run still green")


def test_the_guard_runs_after_the_commit():
    """Placement is deliberate: whatever was captured is saved first, and only
    then does the run go red. scheduled-runs-and-silent-green.md is explicit
    that the guard sits after the commit."""
    text = (WORKFLOWS / "capture.yml").read_text(encoding="utf-8")
    commit = text.find("Commit captured odds")
    guard = text.find("Fail if the line board did not refresh")
    # find(), not index(): a missing guard is the very thing this file is
    # about, and it should read as that failure rather than a ValueError from
    # the assertion's own setup.
    assert guard != -1, "capture.yml has no board guard step at all"
    assert commit != -1 and commit < guard, (
        "a guard before the commit throws away odds we already hold — the "
        "exact loss this workflow exists to prevent")


def test_every_exemption_names_a_step_that_exists():
    """An exemption for a step that has been renamed silently stops guarding
    anything, and reads as a decision that is still being honoured."""
    for fname, prefix in EXEMPT:
        text = (WORKFLOWS / fname).read_text(encoding="utf-8")
        assert any(_name(s).startswith(prefix) for s in _steps(text)), (
            f"EXEMPT names {prefix!r} in {fname}, but no step there is called "
            f"that any more. Re-check whether the exemption still applies.")

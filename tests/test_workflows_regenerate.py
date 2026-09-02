"""A workflow that commits a generated page must also regenerate it.

This exact bug has now shipped three times. seal.yml and grade.yml wrote
data/ledger and committed a stale ledger.html built from it (fixed a536f51).
capture-props.yml appended MLB evidence and committed a props-model.html that
no longer matched (fixed b78e7c31) — except that fix ran the generator without
--render, so it rewrote the payload and left the page behind, and the gate went
red again the next time capture ran.

Every one of those was invisible until a scheduled job turned the gate red
hours later. This is the guard: if a workflow publishes a generated artifact,
the command that generates it has to appear in the same workflow.
"""
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"

# published artifact -> the command that must regenerate it
GENERATORS = {
    "site/public/props-model.html": "scripts/props_model_note.py --render",
    "site/public/ledger.html": "scripts/build_site.py",
    "site/public/verify.html": "scripts/build_site.py",
    "site/public/methodology.html": "scripts/build_site.py",
    "site/public/disclaimers.html": "scripts/build_site.py",
}


@pytest.mark.parametrize("wf", sorted(WORKFLOWS.glob("*.yml")), ids=lambda p: p.name)
def test_committed_pages_are_regenerated_in_the_same_workflow(wf):
    text = wf.read_text(encoding="utf-8")
    for artifact, command in GENERATORS.items():
        if artifact in text:
            assert command in text, (
                f"{wf.name} publishes {artifact} but never runs `{command}`, so "
                f"it will commit whatever stale copy is in the tree. Add the "
                f"regeneration step before the commit step."
            )

"""A broken ledger build must not exit clean.

seal.yml and grade.yml run build_site.py and then commit whatever is on disk.
main() used to catch any exception from build_ledger(), print a warning and
exit 0, so a render bug published the PREVIOUS ledger.html as if it were
current - a superseded root on the one page whose entire job is to be
checkable, and the gate only caught it hours later.
"""
import pytest

import scripts.build_site as build_site


def test_a_broken_ledger_build_exits_nonzero(monkeypatch):
    monkeypatch.setattr(build_site, "build_markdown_pages", lambda *a, **k: None)

    def boom(*a, **k):
        raise RuntimeError("ledger exploded")

    monkeypatch.setattr(build_site, "build_ledger", boom)

    with pytest.raises(SystemExit) as excinfo:
        build_site.main()
    assert "stale ledger.html" in str(excinfo.value), (
        "main() must refuse to exit clean when the ledger build throws; a "
        "workflow would otherwise commit the stale ledger.html")

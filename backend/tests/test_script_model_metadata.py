"""Every script must see every model, or a foreign key it never mentions
cannot be resolved.

This is a guard, like `test_bootstrap_walkthrough.py`. The failure it prevents
is nasty out of proportion to its cause: a script imports the handful of models
it needs, SQLAlchemy resolves foreign keys against the whole of
`Base.metadata`, and the first flush sorts the tables and cannot find one that
nobody imported. The message names the column, not the missing import, and
nothing goes wrong until somebody adds a foreign key that crosses into a module
that particular script never mentions.

That is how `announcements.source_opportunity_id` (ADR 0041) turned the E2E job
red at "seed fictional demo data", a step with nothing to do with the change.
`seed_demo_data.py` had been fine for months only because it happens to import
`Department`, the other end of the one cross-module foreign key announcements
already had.

**It runs in a SUBPROCESS, and that is the whole point.** Asserted in-process
this passes whether or not the fix is present, because `conftest.py` has
already imported the application and with it every model. The bug only exists
in a process that imported the script and nothing else -- which is exactly how
CI runs it.
"""

from __future__ import annotations

import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts

BACKEND = Path(__file__).resolve().parent.parent

#: Scripts are run as `python -m scripts.<name>` from `backend/`.
SCRIPT_MODULES = sorted(
    module.name
    for module in pkgutil.iter_modules(scripts.__path__)
    if not module.name.startswith("_")
)

#: Imported, the foreign keys resolved, nothing executed -- every script guards
#: its work behind `if __name__ == "__main__"`, so importing one is inert.
_PROBE = """
import importlib, sys
importlib.import_module("scripts.{module}")
from app.db.base import Base
from sqlalchemy.orm import configure_mappers

configure_mappers()
broken = []
for table in Base.metadata.tables.values():
    for key in table.foreign_keys:
        try:
            key.column
        except Exception:
            broken.append(table.name + "." + key.parent.name + " -> " + key.target_fullname)
if broken:
    sys.stderr.write("UNRESOLVED: " + "; ".join(sorted(broken)))
    raise SystemExit(1)
"""


def test_there_are_scripts_to_check() -> None:
    """If this ever finds nothing, the walk is broken, not the package."""
    assert len(SCRIPT_MODULES) >= 5, SCRIPT_MODULES


@pytest.mark.parametrize("module", SCRIPT_MODULES)
def test_every_foreign_key_resolves_in_a_fresh_process(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=module)],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"scripts.{module} cannot resolve its foreign keys on its own.\n{result.stderr[-1500:]}"
    )

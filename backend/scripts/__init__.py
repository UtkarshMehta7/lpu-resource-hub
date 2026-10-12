"""Command-line scripts, run as `python -m scripts.<name>` from `backend/`.

Importing the model registry here is load-bearing, not tidiness. A script
imports the handful of models it needs, but SQLAlchemy resolves foreign keys
against the WHOLE of `Base.metadata`: the first flush sorts the tables, and a
table referenced by a model that nobody imported cannot be found. The error
names the column rather than the cause --

    NoReferencedTableError: Foreign key associated with column
    'announcements.source_opportunity_id' could not find table 'opportunities'

-- and it does not appear until a new foreign key crosses into a module that
particular script never mentions. `seed_demo_data.py` had worked for months
only because it happens to import `Department`, which is the other end of the
one cross-module FK announcements had.

So every script gets every model, and adding an FK cannot turn a script red
for reasons that have nothing to do with it.
"""

import app.db.model_registry  # noqa: F401

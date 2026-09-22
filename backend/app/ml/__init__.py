"""Local, explainable matching: structured overlap plus lexical TF-IDF.

Everything here is pure Python over feature dataclasses -- no database, no
FastAPI, no network. `app/modules/recommendations` builds the features from
the database and calls into this package.
"""

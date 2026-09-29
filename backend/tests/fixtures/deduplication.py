"""A labelled fixture for measuring publication de-duplication.

Ground truth is expressed as a **cluster**: records carrying the same cluster
name are the same publication, and every other pair is a genuinely different
one. Pairs are derived from that rather than hand-listed, so the labels cannot
disagree with themselves as the fixture grows.

Every record says which real-world case it represents. The fixture is
deliberately adversarial -- roughly a third of it is *near misses* designed to
be merged by a careless rule: an erratum, a preprint and its published
version, sequel papers, and two different studies with near-identical titles.
A fixture made only of obvious duplicates measures nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.imports.connectors.base import ExternalWork, normalise_doi


@dataclass(frozen=True, slots=True)
class Labelled:
    """One record, and the publication it truly belongs to."""

    #: Records sharing this are the same work. Unique name = a work of its own.
    cluster: str
    #: What this record exercises, for whoever reads a failure.
    case: str
    work: ExternalWork


def _w(
    source: str,
    title: str,
    *,
    doi: str | None = None,
    year: int | None = 2023,
    venue: str | None = None,
    authors: tuple[str, ...] = (),
    abstract: str | None = None,
) -> ExternalWork:
    return ExternalWork(
        source=source,
        title=title,
        # Through the same normaliser every connector applies, so the fixture
        # exercises the algorithm on the shape of data it really receives --
        # a resolver URL or a percent-encoded slash is already resolved by the
        # time merging sees it.
        doi=normalise_doi(doi),
        year=year,
        venue=venue,
        authors=authors,
        abstract=abstract,
    )


FIXTURE: tuple[Labelled, ...] = (
    # --- exact duplicates across sources --------------------------------
    Labelled(
        "graph-survey",
        "exact duplicate, two sources, same DOI",
        _w("orcid", "Deep Learning for Graphs", doi="10.1109/tnn.2021.1", year=2021),
    ),
    Labelled(
        "graph-survey",
        "identical record from a second source",
        _w("openalex", "Deep Learning for Graphs", doi="10.1109/tnn.2021.1", year=2021),
    ),
    Labelled(
        "graph-survey",
        "same DOI, subtitle present, different capitalisation",
        _w(
            "crossref",
            "Deep learning for graphs: a comprehensive survey",
            doi="10.1109/TNN.2021.1",
            year=2021,
            venue="IEEE TNN",
            authors=("A Rao", "B Singh"),
        ),
    ),
    # --- DOI carried in different forms ---------------------------------
    Labelled(
        "soil-sensors",
        "DOI as a bare identifier",
        _w("orcid", "Low-cost soil moisture sensing", doi="10.1016/j.agr.2022.03.004"),
    ),
    Labelled(
        "soil-sensors",
        "same DOI as a resolver URL, percent-encoded slash",
        _w(
            "openalex",
            "Low cost soil-moisture sensing",
            doi="https://doi.org/10.1016%2Fj.agr.2022.03.004",
        ),
    ),
    # --- punctuation and typography -------------------------------------
    Labelled(
        "bose-einstein",
        "no DOI; em dash and colon",
        _w("orcid", "Bose–Einstein Condensation: A Review", doi=None, year=2019),
    ),
    Labelled(
        "bose-einstein",
        "no DOI; hyphen, dash separator, lower case",
        _w("openalex", "bose-einstein condensation - a review", doi=None, year=2019),
    ),
    # --- accents --------------------------------------------------------
    Labelled(
        "schrodinger",
        "no DOI; accented characters",
        _w("orcid", "Schrödinger's Equation Revisited", doi=None, year=2020),
    ),
    Labelled(
        "schrodinger",
        "no DOI; accents stripped, apostrophe dropped",
        _w("openalex", "Schrodingers equation revisited", doi=None, year=2020),
    ),
    # --- word order and dropped subtitle --------------------------------
    Labelled(
        "wheat-yield",
        "no DOI; full title",
        _w("orcid", "Forecasting wheat yield from open satellite data", doi=None, year=2022),
    ),
    Labelled(
        "wheat-yield",
        "no DOI; subtitle dropped by the source",
        _w("crossref", "Forecasting wheat yield", doi=None, year=2022),
    ),
    # --- author variants, same work -------------------------------------
    Labelled(
        "traffic-model",
        "authors given in full",
        _w(
            "orcid",
            "A microscopic model of campus traffic",
            doi="10.1007/s11116-023-10",
            authors=("Priya Nair", "Rahul Verma"),
        ),
    ),
    Labelled(
        "traffic-model",
        "same work, authors initialised",
        _w(
            "openalex",
            "A microscopic model of campus traffic",
            doi="10.1007/s11116-023-10",
            authors=("P. Nair", "R. Verma"),
        ),
    ),
    # --- missing metadata -----------------------------------------------
    Labelled(
        "battery-review",
        "complete record",
        _w(
            "crossref",
            "Solid-state batteries: materials and prospects",
            doi="10.1021/acsenergy.2023.7",
            authors=("K Iyer",),
            venue="ACS Energy Letters",
        ),
    ),
    Labelled(
        "battery-review",
        "same DOI, no authors, no venue",
        _w(
            "orcid", "Solid state batteries materials and prospects", doi="10.1021/acsenergy.2023.7"
        ),
    ),
    # --- malformed records ----------------------------------------------
    Labelled(
        "malformed-doi",
        "malformed DOI, title still usable",
        _w("openalex", "Groundwater recharge in semi-arid basins", doi=None, year=2021),
    ),
    Labelled(
        "malformed-doi",
        "same work; the source supplied an unusable DOI, dropped upstream",
        _w("orcid", "Groundwater recharge in semi arid basins", doi=None, year=2021),
    ),
    Labelled(
        "whitespace-noise",
        "title padded with whitespace and stray punctuation",
        _w("orcid", "  Urban heat islands ...  ", doi=None, year=2020),
    ),
    Labelled(
        "whitespace-noise",
        "clean form of the same title",
        _w("openalex", "Urban heat islands", doi=None, year=2020),
    ),
    # --- NEAR MISSES: must NOT merge ------------------------------------
    Labelled(
        "graph-survey-erratum",
        "erratum: near-identical title, different DOI",
        _w("crossref", "Erratum: Deep learning for graphs", doi="10.1109/tnn.2021.1e", year=2022),
    ),
    Labelled(
        "sensor-part-2",
        "sequel paper; titles differ only by the part number",
        _w("orcid", "Low-cost soil moisture sensing II", doi="10.1016/j.agr.2023.06.009"),
    ),
    Labelled(
        "wheat-maize",
        "different crop, otherwise identical phrasing",
        _w("orcid", "Forecasting maize yield from open satellite data", doi=None, year=2022),
    ),
    Labelled(
        "wheat-2021",
        "same title, different study year, no DOI to separate them",
        _w("openalex", "Forecasting wheat yield from open satellite data", doi=None, year=2021),
    ),
    Labelled(
        "preprint",
        "preprint with its own DOI",
        _w("openalex", "A microscopic model of campus traffic", doi="10.48550/arxiv.2301.001"),
    ),
    Labelled(
        "distinct-battery",
        "different subject, shares three words",
        _w(
            "crossref",
            "Solid-state lighting: materials and prospects",
            doi="10.1021/acsphot.2023.2",
        ),
    ),
    Labelled(
        "editorial-2022",
        "generic title; only the year distinguishes it",
        _w("orcid", "Editorial", doi="10.1000/ed.2022", year=2022),
    ),
    Labelled(
        "editorial-2023",
        "same generic title, a year later, different DOI",
        _w("orcid", "Editorial", doi="10.1000/ed.2023", year=2023),
    ),
    Labelled(
        "review-a",
        "short generic title, distinct work",
        _w("crossref", "Introduction", doi="10.1000/intro.a", year=2021),
    ),
    Labelled(
        "review-b",
        "short generic title, distinct work",
        _w("crossref", "Introduction", doi="10.1000/intro.b", year=2022),
    ),
    # --- singletons -----------------------------------------------------
    Labelled(
        "quantum-codes",
        "unrelated work",
        _w("orcid", "Quantum error correction codes", doi="10.1103/physrev.2020.4"),
    ),
    Labelled(
        "pharma-trial",
        "unrelated work",
        _w("crossref", "A phase II trial of compound X", doi="10.1056/nejm.2021.9"),
    ),
    Labelled(
        "rice-yields",
        "unrelated work, shares a domain word",
        _w("openalex", "Rice yields under changing monsoon patterns", doi="10.1038/s41586-2"),
    ),
)


def ground_truth_pairs() -> set[frozenset[int]]:
    """Every pair of record indices that is genuinely the same publication."""
    pairs: set[frozenset[int]] = set()
    for i, left in enumerate(FIXTURE):
        for j, right in enumerate(FIXTURE):
            if i < j and left.cluster == right.cluster:
                pairs.add(frozenset({i, j}))
    return pairs


__all__ = ["FIXTURE", "Labelled", "ground_truth_pairs"]

"""ORCID public API connector.

ORCID is the identity anchor of the import: the researcher owns the record,
so the name, employments and work list are self-asserted rather than guessed
from a name match. The public API needs no key and no registration.

The JSON is deeply nested and almost every node is nullable, so everything
goes through `_dig`, which walks a path and gives up quietly rather than
raising KeyError three levels down on a record that merely left a field blank.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

import httpx

from app.modules.imports.connectors.base import (
    ConnectorError,
    ExternalProfile,
    ExternalWork,
    ProfileQuery,
    clean,
    normalise_doi,
)

BASE_URL: Final = "https://pub.orcid.org/v3.0"

# 0000-0002-1825-0097 -- four groups of four, last character may be X.
ORCID_RE: Final = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def normalise_orcid(raw: str) -> str | None:
    """Accepts a bare iD or any orcid.org URL form; returns the bare iD."""
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"^https?://(sandbox\.)?orcid\.org/", "", text, flags=re.IGNORECASE)
    text = text.strip("/ ").upper()
    return text if ORCID_RE.match(text) else None


def _dig(node: object, *path: str) -> Any:
    """Walk a chain of dict keys, returning None at the first thing missing."""
    current = node
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _value(node: object, *path: str) -> str | None:
    """ORCID wraps most scalars as {"value": ...}; unwrap and clean."""
    return clean(_dig(node, *path, "value"))


def _items(node: object) -> list[Any]:
    return list(node) if isinstance(node, list) else []


class OrcidConnector:
    name = "orcid"
    label = "ORCID"

    def fetch(self, client: httpx.Client, query: ProfileQuery) -> ExternalProfile | None:
        # ORCID is looked up by iD only. Searching it by name returns
        # namesakes with no way to tell them apart, and silently importing
        # the wrong person's publications is worse than importing nothing.
        if not query.orcid:
            return None
        orcid = normalise_orcid(query.orcid)
        if orcid is None:
            raise ConnectorError("That does not look like an ORCID iD (0000-0000-0000-0000).")

        try:
            response = client.get(
                f"{BASE_URL}/{orcid}/record", headers={"Accept": "application/json"}
            )
        except httpx.HTTPError as exc:
            raise ConnectorError(f"ORCID could not be reached: {exc}") from exc

        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.status_code != httpx.codes.OK:
            raise ConnectorError(f"ORCID answered {response.status_code}.")

        record = response.json()
        if not isinstance(record, Mapping):
            raise ConnectorError("ORCID returned something that is not a record.")

        person = record.get("person")
        activities = record.get("activities-summary")
        designation, affiliation = _employment(activities)

        return ExternalProfile(
            source=self.name,
            source_id=orcid,
            source_url=f"https://orcid.org/{orcid}",
            full_name=_full_name(person),
            designation=designation,
            affiliation=affiliation,
            bio=clean(_dig(person, "biography", "content"), limit=5000),
            links=_links(person),
            topics=_keywords(person),
            works=_works(activities),
        )


def _full_name(person: object) -> str | None:
    credit = _value(person, "name", "credit-name")
    if credit:
        return credit
    given = _value(person, "name", "given-names")
    family = _value(person, "name", "family-name")
    joined = " ".join(part for part in (given, family) if part)
    return clean(joined)


def _employment(activities: object) -> tuple[str | None, str | None]:
    """The most recent employment, as (role title, organisation).

    ORCID groups employments and orders them newest-first within a group, so
    the first summary of the first group is the current post in practice.
    """
    for group in _items(_dig(activities, "employments", "affiliation-group")):
        for summary in _items(_dig(group, "summaries")):
            employment = _dig(summary, "employment-summary")
            if employment is None:
                continue
            role = clean(_dig(employment, "role-title"), limit=150)
            organisation = clean(_dig(employment, "organization", "name"), limit=200)
            department = clean(_dig(employment, "department-name"), limit=200)
            place = ", ".join(part for part in (department, organisation) if part)
            if role or place:
                return role, clean(place, limit=200)
    return None, None


def _links(person: object) -> tuple[tuple[str, str], ...]:
    links: list[tuple[str, str]] = []
    for entry in _items(_dig(person, "researcher-urls", "researcher-url")):
        url = _value(entry, "url")
        if not url:
            continue
        label = clean(_dig(entry, "url-name"), limit=100) or "Website"
        links.append((label, url[:2000]))
    return tuple(links)


def _keywords(person: object) -> tuple[str, ...]:
    found: list[str] = []
    for entry in _items(_dig(person, "keywords", "keyword")):
        # ORCID lets people cram a comma-separated list into one keyword.
        raw = _value(entry, "content") or ""
        for part in raw.split(","):
            cleaned = clean(part, limit=100)
            if cleaned:
                found.append(cleaned)
    return tuple(dict.fromkeys(found))


def _works(activities: object) -> tuple[ExternalWork, ...]:
    works: list[ExternalWork] = []
    for group in _items(_dig(activities, "works", "group")):
        summaries = _items(_dig(group, "work-summary"))
        if not summaries:
            continue
        summary = summaries[0]
        title = _value(summary, "title", "title")
        if not title:
            continue
        works.append(
            ExternalWork(
                source="orcid",
                title=title[:500],
                doi=_doi(_dig(group, "external-ids", "external-id")),
                venue=_value(summary, "journal-title"),
                year=_year(_value(summary, "publication-date", "year")),
                pub_type=clean(_dig(summary, "type")),
                url=_value(summary, "url"),
            )
        )
    return tuple(works)


def _doi(external_ids: object) -> str | None:
    for entry in _items(external_ids):
        if clean(_dig(entry, "external-id-type")) != "doi":
            continue
        value = normalise_doi(
            _value(entry, "external-id-normalized") or _dig(entry, "external-id-value")
        )
        if value:
            return value
    return None


def _year(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        year = int(value)
    except ValueError:
        return None
    # Anything outside this is a data error, not a publication.
    return year if 1500 <= year <= 2200 else None


__all__ = ["OrcidConnector", "normalise_orcid", "ORCID_RE"]

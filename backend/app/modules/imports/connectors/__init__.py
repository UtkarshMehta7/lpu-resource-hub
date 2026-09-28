from app.modules.imports.connectors.base import (
    AuthorCandidate,
    ConnectorError,
    ExternalProfile,
    ExternalWork,
    ProfileConnector,
    ProfileQuery,
    build_client,
)
from app.modules.imports.connectors.crossref import CrossrefConnector
from app.modules.imports.connectors.openalex import OpenAlexConnector
from app.modules.imports.connectors.orcid import OrcidConnector, normalise_orcid
from app.modules.imports.connectors.semantic_scholar import SemanticScholarConnector

__all__ = [
    "AuthorCandidate",
    "ConnectorError",
    "CrossrefConnector",
    "ExternalProfile",
    "ExternalWork",
    "OpenAlexConnector",
    "OrcidConnector",
    "ProfileConnector",
    "ProfileQuery",
    "SemanticScholarConnector",
    "build_client",
    "normalise_orcid",
]

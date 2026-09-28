"""Stateless AGIRA RA JSON/fixed-width translation package."""

from .service import AgiraDocumentKind, RenderedDocument, agira_to_json, json_to_agira

__all__ = [
    "AgiraDocumentKind",
    "RenderedDocument",
    "agira_to_json",
    "json_to_agira",
    "__version__",
]
__version__ = "0.2.0"

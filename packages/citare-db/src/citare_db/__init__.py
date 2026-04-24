"""Citare DB — SQLite schema + ingestion + reference parser + resolver."""
from citare_db.schema import SCHEMA_SQL, init_db
from citare_db.ingest import (
    IngestReport,
    ingest_extraction,
    ingest_extraction_file,
    classify_identifier,
)
from citare_db.parser import parse as parse_reference, ParsedReference, PARSER_VERSION
from citare_db.resolver import resolve_citations, ResolverReport

__all__ = [
    "SCHEMA_SQL",
    "init_db",
    "IngestReport",
    "ingest_extraction",
    "ingest_extraction_file",
    "classify_identifier",
    "parse_reference",
    "ParsedReference",
    "PARSER_VERSION",
    "resolve_citations",
    "ResolverReport",
]

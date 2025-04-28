import pytest
from src.agents.metadata_agent import MetadataAgent

def test_scrub_redact():
    agent = MetadataAgent()
    metadata = {"title": "Doc", "author": "Alice", "created": "2024-01-01", "doc_type": "report", "tags": ["ai"]}
    scrubbed = agent.scrub(metadata, fields=["author", "created"], mode="redact")
    assert scrubbed["author"] == "REDACTED"
    assert scrubbed["created"] == "REDACTED"
    assert scrubbed["title"] == "Doc"

def test_scrub_remove():
    agent = MetadataAgent()
    metadata = {"title": "Doc", "author": "Alice", "created": "2024-01-01", "doc_type": "report", "tags": ["ai"]}
    scrubbed = agent.scrub(metadata, fields=["author", "created"], mode="remove")
    assert "author" not in scrubbed
    assert "created" not in scrubbed
    assert scrubbed["title"] == "Doc"

def test_scrub_none():
    agent = MetadataAgent()
    metadata = {"title": "Doc", "author": "Alice", "created": "2024-01-01", "doc_type": "report", "tags": ["ai"]}
    scrubbed = agent.scrub(metadata, fields=["author", "created"], mode="none")
    assert scrubbed["author"] == "Alice"
    assert scrubbed["created"] == "2024-01-01"

def test_scrub_custom_fields():
    agent = MetadataAgent()
    metadata = {"title": "Doc", "author": "Alice", "created": "2024-01-01", "doc_type": "report", "tags": ["ai"], "secret": "top"}
    scrubbed = agent.scrub(metadata, fields=["secret"], mode="redact")
    assert scrubbed["secret"] == "REDACTED"

def test_enrich_and_validate():
    agent = MetadataAgent()
    incomplete = {"title": "Doc"}
    enriched = agent.enrich(incomplete)
    assert all(field in enriched for field in agent.SCHEMA)
    assert agent.validate(enriched) 
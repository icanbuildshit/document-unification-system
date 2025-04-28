import os
import pytest
import asyncio
from src.agents.orchestrator import OrchestratorAgent

@pytest.mark.skipif(
    not (os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_KEY')),
    reason="Supabase credentials not set; skipping integration test."
)
def test_integration_pipeline():
    # Use the correct test file
    sample_file = 'data/input/test_page.pdf'
    if not os.path.exists(sample_file):
        pytest.skip(f"Sample file {sample_file} not found.")

    orchestrator = OrchestratorAgent(
        scrub_metadata=True,
        scrub_fields=["author", "created"],
        scrub_mode="redact"
    )
    result = asyncio.run(orchestrator.process_document(sample_file, document_id="integration_test_doc"))
    print("Integration pipeline result:", result)
    assert result["status"] == "complete"
    assert isinstance(result["chunk_ids"], list)
    assert result["num_chunks"] == len(result["chunk_ids"]) 
import pytest
from unittest.mock import patch, MagicMock
from src.agents.orchestrator import OrchestratorAgent

def test_orchestrator_pipeline():
    # Mock data
    file_path = "mock.pdf"
    document_id = "mock_doc"
    mock_elements = [
        {"text_content": "A", "coordinates": {"x": 0, "y": 0}},
        {"text_content": "B", "coordinates": {"x": 100, "y": 100}},
    ]
    mock_chunks = [[mock_elements[0]], [mock_elements[1]]]
    mock_keywords = ["ai", "ml"]

    with patch("src.agents.orchestrator.ParserAgent") as MockParser, \
         patch("src.agents.orchestrator.HybridChunker") as MockChunker, \
         patch("src.agents.orchestrator.KeywordExtractor") as MockKeyworder, \
         patch("src.agents.orchestrator.SupabaseStorage") as MockStorage:
        # Set up mocks
        parser_instance = MockParser.return_value
        parser_instance.process.return_value = {
            "documents": [{
                "file_name": document_id,
                "content": {"chunks": mock_elements}
            }]
        }
        chunker_instance = MockChunker.return_value
        chunker_instance.chunk.return_value = mock_chunks
        keyworder_instance = MockKeyworder.return_value
        keyworder_instance.extract_keywords.return_value = mock_keywords
        storage_instance = MockStorage.return_value
        storage_instance.store_chunk.return_value = None
        storage_instance.store_keywords.return_value = None

        orchestrator = OrchestratorAgent()
        result = orchestrator.process_document(file_path)

        # Assertions
        assert result["document_id"] == document_id
        assert result["num_chunks"] == 2
        assert result["status"] == "complete"
        assert len(result["chunk_ids"]) == 2
        parser_instance.process.assert_called_once()
        chunker_instance.chunk.assert_called_once()
        assert keyworder_instance.extract_keywords.call_count == 2
        assert storage_instance.store_chunk.call_count == 2
        assert storage_instance.store_keywords.call_count == 2 
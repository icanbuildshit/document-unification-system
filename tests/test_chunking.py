import pytest
from src.agents.chunking import HybridChunker

@pytest.mark.parametrize("elements", [
    [
        {"text_content": "Introduction to AI", "coordinates": {"x": 100, "y": 100}},
        {"text_content": "Machine learning basics", "coordinates": {"x": 120, "y": 120}},
        {"text_content": "Deep learning overview", "coordinates": {"x": 800, "y": 100}},
        {"text_content": "Neural networks", "coordinates": {"x": 820, "y": 120}},
    ]
])
def test_hybrid_chunking(elements):
    chunker = HybridChunker()
    chunks = chunker.chunk(elements)
    print("Chunks:", chunks)
    # Assert that we get at least 2 clusters (since two spatially separated groups)
    assert len(chunks) >= 2
    # Assert that all elements are assigned to a chunk
    assert sum(len(chunk) for chunk in chunks) == len(elements) 
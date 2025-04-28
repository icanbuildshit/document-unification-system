"""Tests for the Parser Agent."""

import os
import glob
import pytest
from src.agents.parser_agent import ParserAgent

# Find the first PDF in data/input/
pdf_files = glob.glob(os.path.join('data', 'input', '*.pdf'))
SAMPLE_PDF = pdf_files[0] if pdf_files else None

@pytest.mark.asyncio
async def test_pdf_processing():
    assert SAMPLE_PDF is not None, "No PDF files found in data/input/. Please add at least one PDF."
    agent = ParserAgent()
    result = await agent.process([SAMPLE_PDF])
    assert result["metadata"]["successful_parses"] == 1
    assert result["documents"][0]["status"] == "success"
    assert "chunks" in result["documents"][0]["content"]
    print("\nParsed content:", result["documents"][0]["content"])

if __name__ == '__main__':
    pytest.main() 
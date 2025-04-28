import os
from typing import Dict, List, Any, Optional
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.docx import partition_docx
from unstructured.partition.html import partition_html
import pdfplumber
import time
from src.agents.base_agent import BaseAgent
from loguru import logger

class ParserAgent(BaseAgent):
    """
    Agent responsible for parsing different document formats and extracting
    structured content with layout preservation.
    TODO:
    - Add more robust error handling and logging for production use.
    - Support additional formats and custom parsing strategies.
    - Integrate with distributed task queues if needed.
    """
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("parser", config)
        self.supported_formats = self.config.get("supported_formats", ["pdf", "docx", "html"])
        self.extraction_quality = self.config.get("extraction_quality", "high")
    async def process(self, input_files: List[str]) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"Processing {len(input_files)} input documents")
        results = {
            "documents": [],
            "metadata": {
                "total_documents": len(input_files),
                "successful_parses": 0,
                "failed_parses": 0,
                "unsupported_formats": 0
            }
        }
        for file_path in input_files:
            try:
                file_ext = os.path.splitext(file_path)[1].lower().replace('.', '')
                if file_ext not in self.supported_formats:
                    logger.warning(f"Unsupported file format: {file_ext} for file {file_path}")
                    results["metadata"]["unsupported_formats"] += 1
                    continue
                logger.info(f"Parsing document: {file_path}")
                if file_ext == "pdf":
                    doc_content = self._process_pdf(file_path)
                elif file_ext == "docx":
                    doc_content = self._process_docx(file_path)
                elif file_ext == "html":
                    doc_content = self._process_html(file_path)
                else:
                    raise ValueError(f"Unsupported format: {file_ext}")
                content_path = self._save_intermediate_output(
                    doc_content, 
                    f"parsed_{os.path.basename(file_path)}"
                )
                results["documents"].append({
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "content": doc_content,
                    "content_path": content_path,
                    "format": file_ext,
                    "status": "success"
                })
                results["metadata"]["successful_parses"] += 1
            except Exception as e:
                logger.error(f"Failed to parse {file_path}: {str(e)}")
                results["metadata"]["failed_parses"] += 1
                results["documents"].append({
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "status": "error",
                    "error_message": str(e)
                })
        return results
    def _process_pdf(self, file_path: str) -> Dict[str, Any]:
        result = {
            "metadata": {},
            "chunks": [],
            "tables": [],
            "images": []
        }
        elements = partition_pdf(
            file_path, 
            extract_images=self.extraction_quality == "high",
            infer_table_structure=True
        )
        for element in elements:
            if element.category == "Table":
                table_data = {
                    "content": element.text,
                    "metadata": {
                        "page_number": getattr(element, "page_number", None),
                        "coordinates": getattr(element, "coordinates", None)
                    }
                }
                result["tables"].append(table_data)
            elif element.category == "Image":
                image_data = {
                    "metadata": {
                        "page_number": getattr(element, "page_number", None),
                        "coordinates": getattr(element, "coordinates", None)
                    }
                }
                result["images"].append(image_data)
            else:
                chunk = {
                    "text": element.text,
                    "metadata": {
                        "type": element.category,
                        "page_number": getattr(element, "page_number", None),
                        "coordinates": getattr(element, "coordinates", None),
                        "element_id": f"chunk_{len(result['chunks'])}"
                    }
                }
                result["chunks"].append(chunk)
        return result
    def _process_docx(self, file_path: str) -> Dict[str, Any]:
        result = {
            "metadata": {},
            "chunks": []
        }
        elements = partition_docx(file_path)
        for element in elements:
            chunk = {
                "text": element.text,
                "metadata": {
                    "type": element.category,
                    "element_id": f"chunk_{len(result['chunks'])}"
                }
            }
            result["chunks"].append(chunk)
        return result
    def _process_html(self, file_path: str) -> Dict[str, Any]:
        result = {
            "metadata": {},
            "chunks": []
        }
        elements = partition_html(file_path)
        for element in elements:
            chunk = {
                "text": element.text,
                "metadata": {
                    "type": element.category,
                    "element_id": f"chunk_{len(result['chunks'])}"
                }
            }
            result["chunks"].append(chunk)
        return result

class ParsingAgent:
    """
    Specialized agent for document parsing, for use in multi-agent orchestration.
    TODO:
    - Add async support for large-scale ingestion.
    - Add pre/post-processing hooks for custom workflows.
    - Integrate with monitoring and audit systems.
    """
    def __init__(self, config=None):
        self.agent = ParserAgent(config)

    def process(self, file_paths):
        """
        Parse documents and return parsed elements.
        Args:
            file_paths (list): List of file paths.
        Returns:
            dict: Parsed document structure.
        """
        return self.agent.process(file_paths) 
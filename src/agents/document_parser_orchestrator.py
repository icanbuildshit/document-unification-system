"""
Document Parser Orchestrator for coordinating document parsing operations.

This orchestrator is responsible for:
1. Detecting document formats
2. Routing to appropriate parser agents
3. Validating parser output
4. Handling parsing failures and retries
5. Coordinating with other orchestrators for document processing
"""

import os
import uuid
import time
import json
import asyncio
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Tuple, Set
from pathlib import Path
import mimetypes
import hashlib
from contextlib import contextmanager

# LangChain imports
from langchain.document_loaders import (
    PyPDFLoader, 
    Docx2txtLoader, 
    UnstructuredHTMLLoader, 
    CSVLoader,
    TextLoader,
    UnstructuredExcelLoader,
    UnstructuredPowerPointLoader
)
from langchain.schema.document import Document

# Local imports
from src.utils.orchestrator_logging import setup_logger
from src.utils.orchestrator_communication import (
    OrchestrationMessage,
    MessageType,
    OrchestrationStatus,
    OrchestratorAction
)
from src.utils.orchestrator_schema import RequestMetadata, ResponseMetadata
from src.utils.orchestrator_fallback import handling_exceptions
from src.agents.parser_agent import ParserAgent
from src.agents.chunking import ChunkingAgent, DocumentElement, DocumentChunk, ChunkingConfig

# Set up logger
logger = setup_logger("document_parser_orchestrator")


class DocumentMetadata(Dict[str, Any]):
    """Document metadata container with helper methods."""
    
    @property
    def document_id(self) -> str:
        """Get document ID."""
        return self.get("document_id", "")
    
    @property
    def mimetype(self) -> str:
        """Get document mimetype."""
        return self.get("mimetype", "")
    
    @property
    def file_extension(self) -> str:
        """Get file extension."""
        return self.get("file_extension", "")
    
    @property
    def document_type(self) -> str:
        """Get document type."""
        return self.get("document_type", "")
    
    @property
    def page_count(self) -> int:
        """Get page count."""
        return self.get("page_count", 0)
    
    @property
    def word_count(self) -> int:
        """Get word count."""
        return self.get("word_count", 0)
    
    @property
    def is_ocr_needed(self) -> bool:
        """Check if OCR is needed."""
        return self.get("is_ocr_needed", False)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return dict(self)


class ParserOptions(Dict[str, Any]):
    """Parser options container."""
    
    @classmethod
    def default(cls) -> 'ParserOptions':
        """Create default parser options."""
        return cls({
            "extract_tables": True,
            "extract_images": False,
            "perform_ocr": True,
            "ocr_languages": ["eng"],
            "extract_metadata": True,
            "min_text_length": 10,
            "chunk_documents": True,
            "chunking_config": None,  # Use default if None
            "ignore_headers_footers": True,
            "detect_formatting": True,
            "extract_page_numbers": True
        })


class ParseResult:
    """Container for parsing results."""
    
    def __init__(
        self,
        document_id: str,
        original_path: str,
        parsed_elements: List[Dict[str, Any]] = None,
        chunks: List[Dict[str, Any]] = None,
        metadata: Dict[str, Any] = None,
        output_paths: Dict[str, str] = None,
        status: str = "success",
        error: Optional[str] = None
    ):
        self.document_id = document_id
        self.original_path = original_path
        self.parsed_elements = parsed_elements or []
        self.chunks = chunks or []
        self.metadata = metadata or {}
        self.output_paths = output_paths or {}
        self.status = status
        self.error = error
        self.processing_time = 0
        self.timestamp = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "document_id": self.document_id,
            "original_path": self.original_path,
            "parsed_elements": self.parsed_elements,
            "chunks": self.chunks,
            "metadata": self.metadata,
            "output_paths": self.output_paths,
            "status": self.status,
            "error": self.error,
            "processing_time": self.processing_time,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParseResult':
        """Create from dictionary."""
        result = cls(
            document_id=data.get("document_id", ""),
            original_path=data.get("original_path", ""),
            parsed_elements=data.get("parsed_elements", []),
            chunks=data.get("chunks", []),
            metadata=data.get("metadata", {}),
            output_paths=data.get("output_paths", {}),
            status=data.get("status", "unknown"),
            error=data.get("error")
        )
        result.processing_time = data.get("processing_time", 0)
        result.timestamp = data.get("timestamp", datetime.utcnow().isoformat() + "Z")
        return result


class DocumentParserOrchestrator:
    """
    Orchestrates document parsing operations across different formats and parser agents.
    
    Integrates with LangChain for document loading and processing.
    Coordinates chunking and metadata extraction through specialized agents.
    Implements fault-tolerant parsing with retries and fallbacks.
    """
    
    def __init__(
        self,
        base_output_dir: str = None,
        supported_formats: Set[str] = None,
        max_retries: int = 3,
        retry_delay: int = 2
    ):
        """
        Initialize the document parser orchestrator.
        
        Args:
            base_output_dir: Base directory for parser outputs
            supported_formats: Set of supported document formats
            max_retries: Maximum number of parsing retries
            retry_delay: Delay between retries in seconds
        """
        self.orchestrator_id = f"doc-parser-orch-{uuid.uuid4().hex[:8]}"
        
        # Output directory setup
        self.base_output_dir = base_output_dir or os.environ.get(
            "PARSER_OUTPUT_DIR", 
            os.path.join("output", "intermediate", "parser")
        )
        os.makedirs(self.base_output_dir, exist_ok=True)
        
        # Supported formats
        self.supported_formats = supported_formats or {
            "pdf", "docx", "html", "txt", "csv", "xlsx", "pptx", "md"
        }
        
        # Error handling
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # Initialize agents
        self.parser_agent = ParserAgent()
        self.chunking_agent = ChunkingAgent()
        
        # File type detection
        mimetypes.init()
        
        # Active requests tracking
        self.active_requests = {}
        
        logger.info(f"Document Parser Orchestrator {self.orchestrator_id} initialized.")
    
    async def parse_document(
        self, 
        document_path: str, 
        document_id: Optional[str] = None,
        parse_options: Optional[Dict[str, Any]] = None
    ) -> ParseResult:
        """
        Parse a document according to specified options.
        
        Args:
            document_path: Path to the document file
            document_id: ID of the document (auto-generated if not provided)
            parse_options: Dictionary of parsing options
            
        Returns:
            ParseResult object containing parsing results
        """
        start_time = time.time()
        
        # Generate document ID if not provided
        if not document_id:
            document_id = self._generate_document_id(document_path)
        
        # Use default options if not provided
        options = ParserOptions.default()
        if parse_options:
            options.update(parse_options)
        
        # Initialize request tracking
        request_id = str(uuid.uuid4())
        self.active_requests[request_id] = {
            "document_id": document_id,
            "status": "started",
            "start_time": start_time,
            "progress": 0
        }
        
        logger.info(f"Parsing document {document_id} at {document_path} with request_id: {request_id}")
        
        # Verify the document exists
        if not os.path.exists(document_path):
            error_msg = f"Document not found at path: {document_path}"
            logger.error(error_msg)
            self._update_request_status(request_id, "failed", error=error_msg)
            return ParseResult(
                document_id=document_id,
                original_path=document_path,
                status="error",
                error=error_msg
            )
        
        # Verify the format is supported
        document_format = self._get_document_format(document_path)
        if document_format.lower() not in self.supported_formats:
            error_msg = f"Unsupported document format: {document_format}"
            logger.error(error_msg)
            self._update_request_status(request_id, "failed", error=error_msg)
            return ParseResult(
                document_id=document_id,
                original_path=document_path,
                status="error",
                error=error_msg
            )
        
        # Process the document with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                # Update request status
                self._update_request_status(request_id, "processing", progress=10 * attempt)
                
                # Process the document
                result = await self._process_document(document_path, document_id, document_format, options)
                
                # Calculate processing time
                processing_time = time.time() - start_time
                result.processing_time = processing_time
                
                # Save results
                output_path = self._save_parsing_results(result)
                result.output_paths["parsed_json"] = output_path
                
                # Update request status
                self._update_request_status(request_id, "completed", progress=100)
                
                logger.info(f"Successfully parsed document {document_id} in {processing_time:.2f} seconds")
                return result
                
            except Exception as e:
                logger.error(f"Error parsing document {document_id} (attempt {attempt}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_delay} seconds...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    error_msg = f"Failed to parse document after {self.max_retries} attempts: {str(e)}"
                    logger.error(error_msg)
                    self._update_request_status(request_id, "failed", error=error_msg)
                    
                    # Return error result
                    error_result = ParseResult(
                        document_id=document_id,
                        original_path=document_path,
                        status="error",
                        error=error_msg,
                        metadata=self._extract_basic_metadata(document_path, document_format)
                    )
                    error_result.processing_time = time.time() - start_time
                    
                    # Save minimal error result
                    error_output_path = self._save_parsing_results(error_result)
                    error_result.output_paths["error_json"] = error_output_path
                    
                    return error_result
    
    async def _process_document(
        self, 
        document_path: str, 
        document_id: str, 
        document_format: str,
        options: ParserOptions
    ) -> ParseResult:
        """
        Process a document using the appropriate parser and chunking methods.
        
        Args:
            document_path: Path to the document
            document_id: Document identifier
            document_format: Format of the document (pdf, docx, etc.)
            options: Parsing options
            
        Returns:
            ParseResult containing the parsing results
        """
        # Get the appropriate document loader
        loader = self._get_document_loader(document_path, document_format)
        
        # Load the document
        logger.info(f"Loading document {document_id} using {loader.__class__.__name__}")
        
        try:
            # Use LangChain document loader
            langchain_docs = loader.load()
            logger.info(f"Loaded {len(langchain_docs)} pages/segments from {document_id}")
            
            # Extract metadata from document
            metadata = self._extract_metadata(document_path, document_format, langchain_docs)
            metadata["document_id"] = document_id
            
            # Check if OCR is needed based on metadata
            if metadata.get("is_ocr_needed", False) and options.get("perform_ocr", True):
                logger.info(f"Document {document_id} requires OCR processing")
                # TODO: Implement OCR processing
                metadata["ocr_performed"] = True
            
            # Parse the document into structured elements using parser agent
            parsed_elements = await self._parse_with_agent(document_path, langchain_docs, options)
            logger.info(f"Parsed {len(parsed_elements)} elements from document {document_id}")
            
            # Apply chunking if enabled
            chunks = []
            if options.get("chunk_documents", True):
                chunking_config = options.get("chunking_config")
                chunks = await self._chunk_document(parsed_elements, document_id, chunking_config)
                logger.info(f"Created {len(chunks)} chunks from document {document_id}")
            
            # Create the result object
            result = ParseResult(
                document_id=document_id,
                original_path=document_path,
                parsed_elements=[elem.dict() if hasattr(elem, 'dict') else elem for elem in parsed_elements],
                chunks=[chunk.dict() if hasattr(chunk, 'dict') else chunk for chunk in chunks],
                metadata=metadata,
                status="success"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _get_document_loader(self, document_path: str, document_format: str):
        """
        Get the appropriate LangChain document loader for the file type.
        
        Args:
            document_path: Path to the document
            document_format: Format of the document
            
        Returns:
            LangChain document loader
        """
        format_lower = document_format.lower()
        
        # Map document formats to LangChain loaders
        loaders = {
            "pdf": lambda path: PyPDFLoader(path),
            "docx": lambda path: Docx2txtLoader(path),
            "doc": lambda path: Docx2txtLoader(path),  # Fallback to docx loader
            "html": lambda path: UnstructuredHTMLLoader(path),
            "htm": lambda path: UnstructuredHTMLLoader(path),
            "csv": lambda path: CSVLoader(path),
            "txt": lambda path: TextLoader(path),
            "md": lambda path: TextLoader(path),
            "xlsx": lambda path: UnstructuredExcelLoader(path),
            "xls": lambda path: UnstructuredExcelLoader(path),
            "pptx": lambda path: UnstructuredPowerPointLoader(path),
            "ppt": lambda path: UnstructuredPowerPointLoader(path)
        }
        
        if format_lower in loaders:
            return loaders[format_lower](document_path)
        else:
            # Default to text loader for unsupported formats
            logger.warning(f"No specific loader for format {format_lower}, defaulting to TextLoader")
            return TextLoader(document_path)
    
    async def _parse_with_agent(
        self, 
        document_path: str, 
        langchain_docs: List[Document],
        options: ParserOptions
    ) -> List[Dict[str, Any]]:
        """
        Parse the document using the parser agent.
        
        Args:
            document_path: Path to the document
            langchain_docs: LangChain document objects
            options: Parsing options
            
        Returns:
            List of parsed document elements
        """
        # Convert LangChain documents to a format expected by the parser agent
        agent_docs = []
        for i, doc in enumerate(langchain_docs):
            # Extract page number if available in metadata
            page_num = doc.metadata.get("page") or i + 1
            
            agent_docs.append({
                "content": doc.page_content,
                "page_number": page_num,
                "metadata": doc.metadata
            })
        
        # Use the parser agent to extract structured elements
        with handling_exceptions("Parser agent processing", default_return=[]):
            parsing_options = {
                "extract_tables": options.get("extract_tables", True),
                "extract_images": options.get("extract_images", False),
                "min_text_length": options.get("min_text_length", 10),
                "detect_formatting": options.get("detect_formatting", True),
                "extract_page_numbers": options.get("extract_page_numbers", True)
            }
            
            parsed_elements = await asyncio.to_thread(
                self.parser_agent.parse_document,
                document_path=document_path,
                document_segments=agent_docs,
                options=parsing_options
            )
            
            # Convert parser agent output to DocumentElement objects
            structured_elements = []
            for elem in parsed_elements:
                # Create a document element with appropriate attributes
                element = {
                    "text_content": elem.get("text", ""),
                    "element_type": elem.get("type", "text"),
                    "page_number": elem.get("page_number"),
                    "coordinates": elem.get("coordinates"),
                    "is_header": elem.get("is_header", False),
                    "is_footer": elem.get("is_footer", False),
                    "is_table": elem.get("type") == "table",
                    "font_info": elem.get("font_info", {}),
                    "indentation_level": elem.get("indentation", 0),
                    "metadata": elem.get("metadata", {})
                }
                
                # Skip elements with too little content
                if len(element["text_content"].strip()) < options.get("min_text_length", 10):
                    continue
                
                # Optionally ignore headers and footers
                if options.get("ignore_headers_footers", True) and (element["is_header"] or element["is_footer"]):
                    continue
                
                structured_elements.append(element)
            
            return structured_elements
    
    async def _chunk_document(
        self,
        elements: List[Dict[str, Any]],
        document_id: str,
        chunking_config: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Chunk the document elements using the chunking agent.
        
        Args:
            elements: List of document elements
            document_id: Document identifier
            chunking_config: Configuration for chunking (optional)
            
        Returns:
            List of document chunks
        """
        # Skip chunking if no elements
        if not elements:
            return []
        
        # Use the chunking agent to create semantically coherent chunks
        with handling_exceptions("Chunking agent processing", default_return=[]):
            # Apply chunking asynchronously
            document_chunks = await asyncio.to_thread(
                self.chunking_agent.process,
                elements=elements,
                document_id=document_id
            )
            
            # Convert to serializable dictionaries
            return [
                chunk.dict() if hasattr(chunk, 'dict') else 
                {**chunk.to_dict(), "document_id": document_id} if hasattr(chunk, 'to_dict') else
                chunk
                for chunk in document_chunks
            ]
    
    def _extract_metadata(
        self, 
        document_path: str, 
        document_format: str,
        langchain_docs: List[Document]
    ) -> Dict[str, Any]:
        """
        Extract metadata from the document.
        
        Args:
            document_path: Path to the document
            document_format: Format of the document
            langchain_docs: LangChain document objects
            
        Returns:
            Dictionary of metadata
        """
        # Start with basic file metadata
        metadata = self._extract_basic_metadata(document_path, document_format)
        
        # Add metadata from LangChain documents
        if langchain_docs:
            # Get metadata from the first document
            source_metadata = langchain_docs[0].metadata
            
            # Add relevant fields
            for key in ["source", "title", "author", "subject", "creator", "producer"]:
                if key in source_metadata:
                    metadata[key] = source_metadata[key]
            
            # Add document statistics
            metadata["page_count"] = len(langchain_docs)
            metadata["word_count"] = sum(len(doc.page_content.split()) for doc in langchain_docs)
            metadata["character_count"] = sum(len(doc.page_content) for doc in langchain_docs)
            
            # Add timestamp
            metadata["processed_at"] = datetime.utcnow().isoformat() + "Z"
        
        return metadata
    
    def _extract_basic_metadata(self, document_path: str, document_format: str) -> Dict[str, Any]:
        """
        Extract basic metadata from the document file.
        
        Args:
            document_path: Path to the document
            document_format: Format of the document
            
        Returns:
            Dictionary of basic metadata
        """
        file_stats = os.stat(document_path)
        file_basename = os.path.basename(document_path)
        
        # Get MIME type
        mimetype, _ = mimetypes.guess_type(document_path)
        
        metadata = {
            "filename": file_basename,
            "file_size_bytes": file_stats.st_size,
            "file_extension": document_format.lower(),
            "mimetype": mimetype or f"application/{document_format.lower()}",
            "document_type": document_format.upper(),
            "creation_time": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
            "modification_time": datetime.fromtimestamp(file_stats.st_mtime).isoformat(),
            "is_ocr_needed": document_format.lower() == "pdf"  # Simple heuristic, enhance as needed
        }
        
        # Calculate file hash for idempotent processing
        metadata["file_hash_md5"] = self._calculate_file_hash(document_path)
        
        return metadata
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """
        Calculate MD5 hash of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            MD5 hash as a hexadecimal string
        """
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    def _get_document_format(self, document_path: str) -> str:
        """
        Determine the format of a document from its path.
        
        Args:
            document_path: Path to the document
            
        Returns:
            Document format as a string (pdf, docx, etc.)
        """
        # Get file extension
        _, ext = os.path.splitext(document_path)
        if ext:
            return ext[1:].lower()  # Remove the dot
        
        # If no extension, try to guess from content
        mimetype, _ = mimetypes.guess_type(document_path)
        if mimetype:
            # Map MIME type to format
            mime_to_format = {
                "application/pdf": "pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
                "text/html": "html",
                "text/plain": "txt",
                "text/csv": "csv",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx"
            }
            return mime_to_format.get(mimetype, "unknown")
        
        return "unknown"
    
    def _generate_document_id(self, document_path: str) -> str:
        """
        Generate a unique document ID based on filename and timestamp.
        
        Args:
            document_path: Path to the document
            
        Returns:
            Unique document ID
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.basename(document_path)
        filename_base = os.path.splitext(filename)[0]
        
        # Clean filename for use in ID
        clean_name = "".join(c if c.isalnum() or c in "_-." else "_" for c in filename_base)
        
        # Add random suffix for uniqueness
        random_suffix = uuid.uuid4().hex[:8]
        
        return f"{clean_name}_{timestamp}_{random_suffix}"
    
    def _save_parsing_results(self, result: ParseResult) -> str:
        """
        Save parsing results to a JSON file.
        
        Args:
            result: ParseResult object
            
        Returns:
            Path to the saved JSON file
        """
        # Create output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{result.document_id}_{timestamp}.json"
        output_path = os.path.join(self.base_output_dir, output_filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write results to file
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved parsing results to {output_path}")
        return output_path
    
    def _update_request_status(
        self, 
        request_id: str, 
        status: str, 
        progress: int = None,
        error: str = None
    ) -> None:
        """
        Update the status of an active request.
        
        Args:
            request_id: Request identifier
            status: New status
            progress: Progress percentage (0-100)
            error: Error message if applicable
        """
        if request_id in self.active_requests:
            self.active_requests[request_id]["status"] = status
            if progress is not None:
                self.active_requests[request_id]["progress"] = progress
            if error:
                self.active_requests[request_id]["error"] = error
            
            # Add completion time if status is terminal
            if status in ["completed", "failed"]:
                self.active_requests[request_id]["end_time"] = time.time()
    
    async def get_parser_status(self, request_id: str) -> Dict[str, Any]:
        """
        Get status of a parsing request.
        
        Args:
            request_id: ID of the parsing request
            
        Returns:
            Dictionary with status information
        """
        if request_id in self.active_requests:
            return {**self.active_requests[request_id]}
        
        return {
            "request_id": request_id,
            "status": "not_found",
            "error": "Request ID not found"
        }
    
    async def handle_message(self, message: OrchestrationMessage) -> OrchestrationMessage:
        """
        Handle an orchestration message.
        
        Args:
            message: Incoming orchestration message
            
        Returns:
            Response orchestration message
        """
        logger.info(f"Received message: {message.type} from {message.sender_id}")
        
        # Initialize response metadata
        response_metadata = ResponseMetadata(
            request_id=message.metadata.request_id,
            correlation_id=message.metadata.correlation_id,
            status=OrchestrationStatus.SUCCESS
        )
        
        try:
            # Handle different message types
            if message.type == MessageType.DOCUMENT_PARSE_REQUEST:
                # Extract parameters from payload
                payload = message.payload
                document_path = payload.get("document_path")
                document_id = payload.get("document_id")
                parse_options = payload.get("parse_options", {})
                
                # Validate required parameters
                if not document_path:
                    response_metadata.status = OrchestrationStatus.ERROR
                    response_metadata.error_message = "Missing required parameter: document_path"
                    return OrchestrationMessage(
                        type=MessageType.DOCUMENT_PARSE_RESPONSE,
                        payload={"error": "Missing document_path parameter"},
                        metadata=response_metadata,
                        sender_id=self.orchestrator_id
                    )
                
                # Parse the document
                result = await self.parse_document(document_path, document_id, parse_options)
                
                # Prepare response payload
                response_payload = {
                    "document_id": result.document_id,
                    "status": result.status,
                    "output_paths": result.output_paths,
                    "metadata": result.metadata,
                    "processing_time": result.processing_time
                }
                
                # Add error information if applicable
                if result.status == "error":
                    response_metadata.status = OrchestrationStatus.ERROR
                    response_metadata.error_message = result.error
                    response_payload["error"] = result.error
                
                return OrchestrationMessage(
                    type=MessageType.DOCUMENT_PARSE_RESPONSE,
                    payload=response_payload,
                    metadata=response_metadata,
                    sender_id=self.orchestrator_id
                )
                
            elif message.type == MessageType.PARSER_STATUS_REQUEST:
                # Get parser status
                request_id = message.payload.get("request_id")
                if not request_id:
                    response_metadata.status = OrchestrationStatus.ERROR
                    response_metadata.error_message = "Missing required parameter: request_id"
                    return OrchestrationMessage(
                        type=MessageType.PARSER_STATUS_RESPONSE,
                        payload={"error": "Missing request_id parameter"},
                        metadata=response_metadata,
                        sender_id=self.orchestrator_id
                    )
                
                status = await self.get_parser_status(request_id)
                
                return OrchestrationMessage(
                    type=MessageType.PARSER_STATUS_RESPONSE,
                    payload=status,
                    metadata=response_metadata,
                    sender_id=self.orchestrator_id
                )
                
            else:
                # Unsupported message type
                response_metadata.status = OrchestrationStatus.ERROR
                response_metadata.error_message = f"Unsupported message type: {message.type}"
                
                return OrchestrationMessage(
                    type=MessageType.ERROR,
                    payload={"error": f"Unsupported message type: {message.type}"},
                    metadata=response_metadata,
                    sender_id=self.orchestrator_id
                )
                
        except Exception as e:
            # Handle any exceptions
            error_msg = str(e)
            logger.error(f"Error handling message: {error_msg}")
            logger.error(traceback.format_exc())
            
            response_metadata.status = OrchestrationStatus.ERROR
            response_metadata.error_message = error_msg
            
            return OrchestrationMessage(
                type=MessageType.ERROR,
                payload={"error": error_msg},
                metadata=response_metadata,
                sender_id=self.orchestrator_id
            )
    
    @contextmanager
    def _memory_profile(self, operation_name: str):
        """
        Context manager for memory profiling.
        
        Args:
            operation_name: Name of the operation being profiled
        """
        try:
            import os
            import psutil
            process = psutil.Process(os.getpid())
            start_memory = process.memory_info().rss / 1024 / 1024  # MB
            logger.debug(f"Starting {operation_name}: Memory usage: {start_memory:.2f} MB")
            yield
        except ImportError:
            # psutil not available
            yield
        else:
            end_memory = process.memory_info().rss / 1024 / 1024  # MB
            logger.debug(f"Finished {operation_name}: Memory usage: {end_memory:.2f} MB (Δ {end_memory - start_memory:.2f} MB)")
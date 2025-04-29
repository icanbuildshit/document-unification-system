"""
Document Parser Agent for extracting structured content from various document formats.

This agent handles parsing of different document types, extracting:
- Text content with layout information
- Tables and their structure
- Images and their metadata
- Document structure and hierarchy
- Formatting information
"""

import os
import time
import json
import uuid
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from pathlib import Path

# Parsing libraries
import pdfplumber
from unstructured.partition.pdf import partition_pdf
from unstructured.partition.docx import partition_docx
from unstructured.partition.html import partition_html
from unstructured.partition.pptx import partition_pptx
from unstructured.partition.xlsx import partition_xlsx
from unstructured.staging.base import elements_from_json, elements_to_json
from unstructured.cleaners.core import clean_bullets, clean_extra_whitespace
from unstructured.documents.elements import Table, Title, NarrativeText, Text, ListItem, Image

# Base agent imports
from src.agents.base_agent import BaseAgent
from src.utils.orchestrator_logging import setup_logger

# Set up logger
logger = setup_logger("parser_agent")


class DocumentSegment:
    """A segment of a document (e.g., page, section) with content and metadata."""
    
    def __init__(
        self,
        content: str,
        page_number: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.content = content
        self.page_number = page_number
        self.metadata = metadata or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "content": self.content,
            "page_number": self.page_number,
            "metadata": self.metadata
        }


class ParsedElement:
    """A parsed element from a document with extracted information."""
    
    def __init__(
        self,
        text: str,
        element_type: str = "text",
        page_number: Optional[int] = None,
        coordinates: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        element_id: Optional[str] = None,
        parent_id: Optional[str] = None
    ):
        self.text = text
        self.type = element_type
        self.page_number = page_number
        self.coordinates = coordinates
        self.metadata = metadata or {}
        self.element_id = element_id or str(uuid.uuid4())
        self.parent_id = parent_id
        
        # Special flags for layout information
        self.is_header = False
        self.is_footer = False
        self.indentation = 0
        self.font_info = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "text": self.text,
            "type": self.type,
            "page_number": self.page_number,
            "coordinates": self.coordinates,
            "metadata": self.metadata,
            "element_id": self.element_id,
            "parent_id": self.parent_id,
            "is_header": self.is_header,
            "is_footer": self.is_footer,
            "indentation": self.indentation,
            "font_info": self.font_info
        }


class ParserOptions(Dict[str, Any]):
    """Container for parser options."""
    
    @classmethod
    def default(cls) -> 'ParserOptions':
        """Create default parser options."""
        return cls({
            "extract_tables": True,
            "extract_images": True,
            "detect_formatting": True,
            "extract_page_numbers": True,
            "min_text_length": 10,
            "header_footer_detection": True,
            "clean_text": True,
            "remove_bullets": True,
            "metadata_extraction": True
        })


class ParserAgent(BaseAgent):
    """
    Agent responsible for parsing different document formats and extracting
    structured content with layout preservation.
    
    Features:
    - Support for PDF, DOCX, HTML, PPTX, XLSX formats
    - Extraction of text with layout information
    - Table and image detection
    - Header/footer identification
    - Font and formatting detection
    - Structured output for downstream processing
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the parser agent.
        
        Args:
            config: Configuration dictionary for the agent
        """
        super().__init__("parser", config or {})
        
        # Configure supported formats
        self.supported_formats = self.config.get("supported_formats", [
            "pdf", "docx", "html", "pptx", "xlsx", "txt", "md"
        ])
        
        # Configure extraction quality (affects performance)
        self.extraction_quality = self.config.get("extraction_quality", "high")
        
        # Output directory setup
        self.output_dir = self.config.get("output_dir", os.path.join("data", "intermediate", "parser"))
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Statistics tracking
        self.stats = {
            "documents_processed": 0,
            "successful_parses": 0,
            "failed_parses": 0,
            "elements_extracted": 0,
            "tables_extracted": 0,
            "images_extracted": 0,
            "total_processing_time": 0
        }
        
        logger.info(f"Parser agent initialized with {len(self.supported_formats)} supported formats")
    
    def parse_document(
        self,
        document_path: str = None,
        document_segments: List[Dict[str, Any]] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> List[ParsedElement]:
        """
        Parse a document from file or pre-loaded segments.
        
        Args:
            document_path: Path to the document file to parse (optional if segments provided)
            document_segments: Pre-loaded document segments (optional if path provided)
            options: Parsing options
            
        Returns:
            List of parsed elements from the document
        """
        start_time = time.time()
        
        # Use default options if not provided
        parse_options = ParserOptions.default()
        if options:
            parse_options.update(options)
        
        try:
            # Track document in stats
            self.stats["documents_processed"] += 1
            
            # Parse from file or segments
            if document_path and os.path.exists(document_path):
                logger.info(f"Parsing document from file: {document_path}")
                parsed_elements = self._parse_from_file(document_path, parse_options)
            elif document_segments:
                logger.info(f"Parsing document from {len(document_segments)} pre-loaded segments")
                parsed_elements = self._parse_from_segments(document_segments, parse_options)
            else:
                raise ValueError("Either document_path or document_segments must be provided")
            
            # Apply post-processing
            processed_elements = self._post_process_elements(parsed_elements, parse_options)
            
            # Update stats
            self.stats["successful_parses"] += 1
            self.stats["elements_extracted"] += len(processed_elements)
            
            # Calculate tables and images
            self.stats["tables_extracted"] += sum(1 for elem in processed_elements if elem.type == "table")
            self.stats["images_extracted"] += sum(1 for elem in processed_elements if elem.type == "image")
            
            # Track processing time
            processing_time = time.time() - start_time
            self.stats["total_processing_time"] += processing_time
            
            logger.info(f"Successfully parsed document with {len(processed_elements)} elements in {processing_time:.2f} seconds")
            return processed_elements
            
        except Exception as e:
            # Log error and update stats
            self.stats["failed_parses"] += 1
            logger.error(f"Error parsing document: {str(e)}", exc_info=True)
            
            # Return empty list as fallback
            return []
    
    def _parse_from_file(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Parse a document from a file path.
        
        Args:
            file_path: Path to the document
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        # Determine file format
        file_ext = os.path.splitext(file_path)[1].lower().replace('.', '')
        
        # Check if format is supported
        if file_ext not in self.supported_formats:
            logger.warning(f"Unsupported file format: {file_ext} for file {file_path}")
            return []
        
        # Use appropriate parser for the format
        if file_ext == "pdf":
            return self._process_pdf(file_path, options)
        elif file_ext == "docx":
            return self._process_docx(file_path, options)
        elif file_ext == "html" or file_ext == "htm":
            return self._process_html(file_path, options)
        elif file_ext == "pptx":
            return self._process_pptx(file_path, options)
        elif file_ext == "xlsx" or file_ext == "xls":
            return self._process_xlsx(file_path, options)
        elif file_ext in ["txt", "md"]:
            return self._process_text(file_path, options)
        else:
            logger.warning(f"No specialized parser for format {file_ext}, using text fallback")
            return self._process_text(file_path, options)
    
    def _parse_from_segments(
        self,
        segments: List[Dict[str, Any]],
        options: Dict[str, Any]
    ) -> List[ParsedElement]:
        """
        Parse a document from pre-loaded segments.
        
        Args:
            segments: List of document segments (content with metadata)
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        for i, segment in enumerate(segments):
            # Extract content and metadata
            content = segment.get("content", "")
            page_number = segment.get("page_number", i + 1)
            metadata = segment.get("metadata", {})
            
            # Skip empty content
            if not content.strip():
                continue
            
            # Create basic element
            element = ParsedElement(
                text=content,
                element_type="text",
                page_number=page_number,
                metadata=metadata,
                element_id=f"segment_{i}"
            )
            
            # Apply text cleaning if enabled
            if options.get("clean_text", True):
                element.text = clean_extra_whitespace(element.text)
                if options.get("remove_bullets", True):
                    element.text = clean_bullets(element.text)
            
            # Apply basic formatting detection
            if options.get("detect_formatting", True):
                # Detect titles/headings
                if len(content.strip().splitlines()) == 1 and len(content.strip()) < 100:
                    element.type = "title"
                    element.metadata["heading_level"] = 1
                
                # Detect lists (simple heuristic)
                if content.strip().startswith(("-", "*", "•")) or (
                    content.strip()[0].isdigit() and content.strip()[1:3] in [". ", ") "]
                ):
                    element.type = "list_item"
                    element.indentation = 1
            
            # Add to results
            parsed_elements.append(element)
        
        return parsed_elements
    
    def _process_pdf(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Process a PDF document.
        
        Args:
            file_path: Path to the PDF file
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        # Use Unstructured library for initial parsing
        try:
            # Configure extraction options
            unstructured_options = {
                "extract_images": options.get("extract_images", True) and self.extraction_quality == "high",
                "extract_image_blocks": options.get("extract_images", True),
                "detect_tables": options.get("extract_tables", True),
                "infer_table_structure": options.get("extract_tables", True)
            }
            
            # Parse the PDF
            elements = partition_pdf(file_path, **unstructured_options)
            
            # Process each element
            for i, element in enumerate(elements):
                # Get element text
                text = element.text if hasattr(element, "text") else ""
                
                # Skip elements with insufficient text
                if len(text.strip()) < options.get("min_text_length", 10) and not isinstance(element, (Table, Image)):
                    continue
                
                # Get element type based on class
                if isinstance(element, Table):
                    element_type = "table"
                elif isinstance(element, Image):
                    element_type = "image"
                elif isinstance(element, Title):
                    element_type = "title"
                elif isinstance(element, ListItem):
                    element_type = "list_item"
                elif isinstance(element, NarrativeText):
                    element_type = "paragraph"
                else:
                    element_type = "text"
                
                # Get coordinates if available
                coordinates = None
                if hasattr(element, "coordinates"):
                    coordinates = element.coordinates
                
                # Create parsed element
                parsed_element = ParsedElement(
                    text=text,
                    element_type=element_type,
                    page_number=getattr(element, "page_number", None),
                    coordinates=coordinates,
                    metadata={
                        "category": getattr(element, "category", None),
                        "element_id": f"element_{i}"
                    }
                )
                
                # Process tables specially
                if element_type == "table" and hasattr(element, "metadata"):
                    parsed_element.metadata["table_data"] = element.metadata.get("text_as_html", "")
                
                # Add to results
                parsed_elements.append(parsed_element)
            
            # Use pdfplumber for additional layout information
            if options.get("detect_formatting", True) or options.get("header_footer_detection", True):
                parsed_elements = self._enhance_pdf_with_layout(file_path, parsed_elements, options)
        
        except Exception as e:
            logger.error(f"Error parsing PDF {file_path}: {str(e)}")
            # Use pdfplumber as fallback
            logger.info("Falling back to pdfplumber for basic PDF parsing")
            parsed_elements = self._process_pdf_fallback(file_path, options)
        
        return parsed_elements
    
    def _enhance_pdf_with_layout(
        self,
        file_path: str,
        elements: List[ParsedElement],
        options: Dict[str, Any]
    ) -> List[ParsedElement]:
        """
        Enhance PDF parsing with additional layout information.
        
        Args:
            file_path: Path to the PDF file
            elements: Already parsed elements
            options: Parsing options
            
        Returns:
            Enhanced list of parsed elements
        """
        try:
            with pdfplumber.open(file_path) as pdf:
                # Process each page
                for page_num, page in enumerate(pdf.pages, 1):
                    
                    # Get page dimensions
                    page_width = page.width
                    page_height = page.height
                    
                    # Extract font information
                    page_fonts = {}
                    if page.chars:
                        for char in page.chars:
                            font_name = char.get("fontname", "")
                            font_size = char.get("size", 0)
                            if font_name and font_size:
                                # Map text positions to font info
                                pos_key = f"{round(char['x0'])},{round(char['top'])}"
                                page_fonts[pos_key] = {"font_name": font_name, "font_size": font_size}
                    
                    # Detect headers and footers
                    if options.get("header_footer_detection", True):
                        # Simple heuristic: top 10% of page is header, bottom 10% is footer
                        header_boundary = page_height * 0.1
                        footer_boundary = page_height * 0.9
                        
                        # Mark elements as headers or footers based on position
                        for element in elements:
                            if element.page_number == page_num and element.coordinates:
                                y_coordinate = element.coordinates.get("y0", 0)
                                if y_coordinate < header_boundary:
                                    element.is_header = True
                                    element.metadata["position"] = "header"
                                elif y_coordinate > footer_boundary:
                                    element.is_footer = True
                                    element.metadata["position"] = "footer"
                    
                    # Apply font information to elements
                    if options.get("detect_formatting", True) and page_fonts:
                        for element in elements:
                            if element.page_number == page_num and element.coordinates:
                                # Try to match element position with font info
                                x_pos = round(element.coordinates.get("x0", 0))
                                y_pos = round(element.coordinates.get("y0", 0))
                                pos_key = f"{x_pos},{y_pos}"
                                
                                # If exact match not found, find nearest
                                if pos_key not in page_fonts:
                                    # Find closest font info (simple approach)
                                    min_distance = float('inf')
                                    best_match = None
                                    for font_pos, font_info in page_fonts.items():
                                        fx, fy = map(int, font_pos.split(","))
                                        distance = ((fx - x_pos) ** 2 + (fy - y_pos) ** 2) ** 0.5
                                        if distance < min_distance:
                                            min_distance = distance
                                            best_match = font_info
                                    
                                    if best_match and min_distance < 50:  # Threshold for matching
                                        element.font_info = best_match
                                else:
                                    element.font_info = page_fonts[pos_key]
                                
                                # Enhance element type based on font
                                if element.font_info:
                                    font_size = element.font_info.get("font_size", 0)
                                    # Larger fonts are likely headings
                                    if font_size > 14 and element.type == "text":
                                        element.type = "title"
                                        element.metadata["heading_level"] = 1
                                    elif font_size > 12 and element.type == "text":
                                        element.type = "subtitle"
                                        element.metadata["heading_level"] = 2
        
        except Exception as e:
            logger.error(f"Error enhancing PDF with layout: {str(e)}")
            # Continue with existing elements
            pass
        
        return elements
    
    def _process_pdf_fallback(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Fallback PDF processing using pdfplumber only.
        
        Args:
            file_path: Path to the PDF file
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract text
                    text = page.extract_text() or ""
                    if not text.strip():
                        continue
                    
                    # Split into paragraphs
                    paragraphs = [p for p in text.split("\n\n") if p.strip()]
                    
                    for i, paragraph in enumerate(paragraphs):
                        if len(paragraph.strip()) < options.get("min_text_length", 10):
                            continue
                        
                        # Create element
                        element = ParsedElement(
                            text=paragraph,
                            element_type="paragraph",
                            page_number=page_num,
                            coordinates={"page": page_num},
                            metadata={"source": "pdfplumber_fallback"}
                        )
                        
                        parsed_elements.append(element)
                    
                    # Extract tables if enabled
                    if options.get("extract_tables", True):
                        tables = page.extract_tables()
                        for t_idx, table in enumerate(tables):
                            if not table:
                                continue
                            
                            # Convert table to text
                            table_text = "\n".join(["\t".join([cell or "" for cell in row]) for row in table])
                            
                            # Create table element
                            table_element = ParsedElement(
                                text=table_text,
                                element_type="table",
                                page_number=page_num,
                                coordinates={"page": page_num},
                                metadata={
                                    "source": "pdfplumber_fallback",
                                    "table_index": t_idx,
                                    "row_count": len(table),
                                    "col_count": len(table[0]) if table else 0
                                }
                            )
                            
                            parsed_elements.append(table_element)
        
        except Exception as e:
            logger.error(f"Error in PDF fallback processing: {str(e)}")
        
        return parsed_elements
    
    def _process_docx(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Process a DOCX document.
        
        Args:
            file_path: Path to the DOCX file
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        try:
            # Use Unstructured for DOCX parsing
            elements = partition_docx(file_path)
            
            # Process each element
            for i, element in enumerate(elements):
                # Skip elements with insufficient text
                if len(element.text.strip()) < options.get("min_text_length", 10):
                    continue
                
                # Determine element type
                if isinstance(element, Title):
                    element_type = "title"
                elif isinstance(element, ListItem):
                    element_type = "list_item"
                elif isinstance(element, Table):
                    element_type = "table"
                elif isinstance(element, NarrativeText):
                    element_type = "paragraph"
                else:
                    element_type = "text"
                
                # Create parsed element
                parsed_element = ParsedElement(
                    text=element.text,
                    element_type=element_type,
                    metadata={
                        "category": element.category,
                        "element_id": f"element_{i}"
                    }
                )
                
                # Add indentation for list items
                if element_type == "list_item" and hasattr(element, "metadata"):
                    parsed_element.indentation = element.metadata.get("indentation", 1)
                
                # Add to results
                parsed_elements.append(parsed_element)
        
        except Exception as e:
            logger.error(f"Error processing DOCX {file_path}: {str(e)}")
        
        return parsed_elements
    
    def _process_html(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Process an HTML document.
        
        Args:
            file_path: Path to the HTML file
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        try:
            # Use Unstructured for HTML parsing
            elements = partition_html(file_path)
            
            # Process each element
            for i, element in enumerate(elements):
                # Skip elements with insufficient text
                if len(element.text.strip()) < options.get("min_text_length", 10):
                    continue
                
                # Determine element type
                if isinstance(element, Title):
                    element_type = "title"
                elif isinstance(element, ListItem):
                    element_type = "list_item"
                elif isinstance(element, Table):
                    element_type = "table"
                elif isinstance(element, NarrativeText):
                    element_type = "paragraph"
                else:
                    element_type = "text"
                
                # Create parsed element
                parsed_element = ParsedElement(
                    text=element.text,
                    element_type=element_type,
                    metadata={
                        "category": element.category,
                        "element_id": f"element_{i}",
                        "html_tag": getattr(element, "tag", None) if hasattr(element, "tag") else None
                    }
                )
                
                # Handle indentation for list items
                if element_type == "list_item" and hasattr(element, "metadata"):
                    parsed_element.indentation = element.metadata.get("indentation", 1)
                
                parsed_elements.append(parsed_element)
        
        except Exception as e:
            logger.error(f"Error processing HTML {file_path}: {str(e)}")
        
        return parsed_elements
    
    def _process_pptx(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Process a PPTX document.
        
        Args:
            file_path: Path to the PPTX file
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        try:
            # Use Unstructured for PPTX parsing
            elements = partition_pptx(file_path)
            
            # Track slide numbers
            current_slide = 1
            
            # Process each element
            for i, element in enumerate(elements):
                # Update slide number based on metadata
                if hasattr(element, "metadata") and "page_number" in element.metadata:
                    current_slide = element.metadata["page_number"]
                
                # Skip elements with insufficient text
                if len(element.text.strip()) < options.get("min_text_length", 10):
                    continue
                
                # Determine element type
                if isinstance(element, Title):
                    element_type = "title"
                elif isinstance(element, ListItem):
                    element_type = "list_item"
                elif isinstance(element, Table):
                    element_type = "table"
                else:
                    element_type = "text"
                
                # Create parsed element
                parsed_element = ParsedElement(
                    text=element.text,
                    element_type=element_type,
                    page_number=current_slide,
                    metadata={
                        "category": element.category,
                        "element_id": f"element_{i}",
                        "slide_number": current_slide
                    }
                )
                
                # Add to results
                parsed_elements.append(parsed_element)
        
        except Exception as e:
            logger.error(f"Error processing PPTX {file_path}: {str(e)}")
        
        return parsed_elements
    
    def _process_xlsx(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Process an XLSX document.
        
        Args:
            file_path: Path to the XLSX file
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        try:
            # Use Unstructured for XLSX parsing
            elements = partition_xlsx(file_path)
            
            # Process each element
            for i, element in enumerate(elements):
                # Skip elements with insufficient text
                if len(element.text.strip()) < options.get("min_text_length", 10):
                    continue
                
                # Create parsed element
                parsed_element = ParsedElement(
                    text=element.text,
                    element_type="table" if isinstance(element, Table) else "text",
                    metadata={
                        "category": element.category,
                        "element_id": f"element_{i}",
                        "sheet_name": getattr(element, "metadata", {}).get("sheet_name") if hasattr(element, "metadata") else None
                    }
                )
                
                # Add to results
                parsed_elements.append(parsed_element)
        
        except Exception as e:
            logger.error(f"Error processing XLSX {file_path}: {str(e)}")
        
        return parsed_elements
    
    def _process_text(self, file_path: str, options: Dict[str, Any]) -> List[ParsedElement]:
        """
        Process a text document.
        
        Args:
            file_path: Path to the text file
            options: Parsing options
            
        Returns:
            List of parsed elements
        """
        parsed_elements = []
        
        try:
            # Read the file
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            
            # Split into paragraphs
            paragraphs = [p for p in text.split("\n\n") if p.strip()]
            
            # Process each paragraph
            for i, paragraph in enumerate(paragraphs):
                if len(paragraph.strip()) < options.get("min_text_length", 10):
                    continue
                
                # Determine element type
                element_type = "paragraph"
                
                # Simple heuristic for headings and lists
                if len(paragraph.strip().splitlines()) == 1 and len(paragraph.strip()) < 100:
                    if paragraph.strip().isupper() or paragraph.strip().endswith(':'):
                        element_type = "title"
                
                if paragraph.strip().startswith(("-", "*", "•")) or (
                    paragraph.strip()[0].isdigit() and paragraph.strip()[1:3] in [". ", ") "]
                ):
                    element_type = "list_item"
                
                # Create parsed element
                parsed_element = ParsedElement(
                    text=paragraph,
                    element_type=element_type,
                    metadata={
                        "element_id": f"element_{i}",
                        "source": "text_file"
                    }
                )
                
                # Set indentation for list items
                if element_type == "list_item":
                    parsed_element.indentation = 1
                
                # Add to results
                parsed_elements.append(parsed_element)
        
        except Exception as e:
            logger.error(f"Error processing text file {file_path}: {str(e)}")
        
        return parsed_elements
    
    def _post_process_elements(
        self,
        elements: List[ParsedElement],
        options: Dict[str, Any]
    ) -> List[ParsedElement]:
        """
        Apply post-processing to parsed elements.
        
        Args:
            elements: List of parsed elements
            options: Parsing options
            
        Returns:
            Processed list of elements
        """
        # Skip if no elements
        if not elements:
            return []
        
        # Apply text cleaning if enabled
        if options.get("clean_text", True):
            for element in elements:
                element.text = clean_extra_whitespace(element.text)
                if options.get("remove_bullets", True) and not element.type == "list_item":
                    element.text = clean_bullets(element.text)
        
        # Filter out elements with insufficient text (except tables and images)
        min_length = options.get("min_text_length", 10)
        filtered_elements = [
            element for element in elements
            if len(element.text.strip()) >= min_length or element.type in ["table", "image"]
        ]
        
        # Sort elements by page number if available
        has_page_numbers = any(element.page_number is not None for element in filtered_elements)
        if has_page_numbers and options.get("extract_page_numbers", True):
            # Group by page number
            page_grouped = {}
            for element in filtered_elements:
                page = element.page_number or 0
                if page not in page_grouped:
                    page_grouped[page] = []
                page_grouped[page].append(element)
            
            # Reconstruct list in page order
            sorted_elements = []
            for page in sorted(page_grouped.keys()):
                sorted_elements.extend(page_grouped[page])
            
            return sorted_elements
        
        return filtered_elements
    
    def _save_intermediate_output(self, data: Dict[str, Any], filename: str) -> str:
        """
        Save intermediate parsing output to a file.
        
        Args:
            data: Data to save
            filename: Base filename
            
        Returns:
            Path to the saved file
        """
        # Create timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Clean filename
        clean_name = "".join(c if c.isalnum() or c in "_-." else "_" for c in filename)
        
        # Create output path
        output_path = os.path.join(self.output_dir, f"{clean_name}_{timestamp}.json")
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return output_path
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        if self.stats["documents_processed"] > 0:
            self.stats["avg_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["documents_processed"]
            )
        
        return self.stats
    
    async def process(self, input_files: List[str]) -> Dict[str, Any]:
        """
        Legacy method for compatibility with the BaseAgent interface.
        
        Args:
            input_files: List of file paths
            
        Returns:
            Dictionary of parsing results
        """
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
                # Check file extension
                file_ext = os.path.splitext(file_path)[1].lower().replace('.', '')
                if file_ext not in self.supported_formats:
                    logger.warning(f"Unsupported file format: {file_ext} for file {file_path}")
                    results["metadata"]["unsupported_formats"] += 1
                    continue
                
                # Parse document
                parsed_elements = self.parse_document(file_path)
                
                # Convert to dictionary format
                elements_dict = [element.to_dict() for element in parsed_elements]
                
                # Save intermediate output
                content_path = self._save_intermediate_output(
                    {"elements": elements_dict},
                    f"parsed_{os.path.basename(file_path)}"
                )
                
                # Add to results
                results["documents"].append({
                    "file_path": file_path,
                    "file_name": os.path.basename(file_path),
                    "content": {"elements": elements_dict},
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
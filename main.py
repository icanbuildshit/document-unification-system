"""
Main pipeline for Document Unification System.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

from src.agents.orchestrator import OrchestratorAgent, ProcessingOptions
from src.utils.orchestrator_logging import setup_logger

# Set up logger
logger = setup_logger("main")

try:
    import yaml
except ImportError:
    yaml = None


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from a YAML or JSON file.
    
    Args:
        config_path: Path to the configuration file
        
    Returns:
        Dictionary containing configuration
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    ext = os.path.splitext(config_path)[1].lower()
    with open(config_path, 'r', encoding='utf-8') as f:
        if ext in ['.yaml', '.yml']:
            if not yaml:
                raise ImportError("PyYAML is not installed. Install with 'pip install pyyaml'.")
            return yaml.safe_load(f)
        elif ext == '.json':
            return json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {ext}")


async def process_document(
    file_path: str,
    document_id: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    base_output_dir: Optional[str] = None,
    log_directory: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a document through the complete pipeline.
    
    Args:
        file_path: Path to the document file
        document_id: Optional ID for the document
        options: Processing options
        user_id: Optional user ID for authentication
        base_output_dir: Base directory for outputs
        log_directory: Directory for logs
        
    Returns:
        Result of document processing
    """
    # Create orchestrator
    orchestrator = OrchestratorAgent(
        base_output_dir=base_output_dir,
        default_options=options,
        log_directory=log_directory
    )
    
    # Process the document
    start_time = datetime.now()
    logger.info(f"Starting document processing: {file_path}")
    
    try:
        result = await orchestrator.process_document(
            file_path=file_path,
            document_id=document_id,
            options=options,
            user_id=user_id
        )
        
        # Calculate processing time
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Document processing completed in {processing_time:.2f} seconds")
        
        return result
    
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        raise


async def process_batch(
    file_paths: List[str],
    options: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    base_output_dir: Optional[str] = None,
    log_directory: Optional[str] = None
) -> Dict[str, Any]:
    """
    Process a batch of documents.
    
    Args:
        file_paths: List of document file paths
        options: Processing options
        user_id: Optional user ID for authentication
        base_output_dir: Base directory for outputs
        log_directory: Directory for logs
        
    Returns:
        Dictionary with results for each document
    """
    # Create orchestrator
    orchestrator = OrchestratorAgent(
        base_output_dir=base_output_dir,
        default_options=options,
        log_directory=log_directory
    )
    
    # Process each document
    results = {}
    for file_path in file_paths:
        try:
            document_id = f"doc-{os.path.basename(file_path)}"
            result = await orchestrator.process_document(
                file_path=file_path,
                document_id=document_id,
                options=options,
                user_id=user_id
            )
            results[file_path] = result
        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            results[file_path] = {
                "status": "error",
                "error": str(e)
            }
    
    # Return combined results
    return {
        "batch_size": len(file_paths),
        "successful": sum(1 for r in results.values() if r.get("status") == "success"),
        "failed": sum(1 for r in results.values() if r.get("status") == "error"),
        "results": results
    }


def main():
    """
    Main entry point for the Document Unification System.
    
    Parses command-line arguments, loads configuration, and processes documents.
    """
    parser = argparse.ArgumentParser(description="Document Unification System")
    
    # Input document options
    parser.add_argument("file_path", type=str, nargs="?", help="Path to the input document")
    parser.add_argument("--batch", type=str, help="Path to a directory or a file with a list of documents to process")
    parser.add_argument("--document-id", type=str, default=None, help="Optional document ID")
    
    # Configuration options
    parser.add_argument("--config", type=str, default=None, help="Path to config file (YAML or JSON)")
    parser.add_argument("--output-dir", type=str, default=None, help="Base output directory")
    parser.add_argument("--log-dir", type=str, default=None, help="Log directory")
    
    # Authentication options
    parser.add_argument("--user-id", type=str, default=None, help="User ID for authentication")
    parser.add_argument("--require-auth", action="store_true", help="Require authentication")
    
    # Document parsing options
    parser.add_argument("--extract-tables", action="store_true", help="Extract tables from documents")
    parser.add_argument("--extract-images", action="store_true", help="Extract images from documents")
    parser.add_argument("--perform-ocr", action="store_true", help="Perform OCR on documents")
    parser.add_argument("--no-chunking", action="store_true", help="Disable document chunking")
    
    # Metadata options
    parser.add_argument("--scrub-metadata", action="store_true", help="Enable metadata scrubbing")
    parser.add_argument("--scrub-fields", type=str, default=None, help="Comma-separated list of metadata fields to scrub")
    parser.add_argument("--scrub-mode", type=str, choices=["redact", "remove", "none"], default="redact", help="Metadata scrubbing mode")
    
    # Storage options
    parser.add_argument("--no-storage", action="store_true", help="Disable storage to database")
    parser.add_argument("--encrypt", action="store_true", help="Encrypt sensitive data")
    
    # Publication options
    parser.add_argument("--generate-preview", action="store_true", help="Generate document preview")
    parser.add_argument("--index-for-search", action="store_true", help="Index document for search")
    
    # Advanced options
    parser.add_argument("--use-legacy-flow", action="store_true", help="Use legacy processing flow instead of orchestrated flow")
    parser.add_argument("--audit-level", type=str, choices=["basic", "standard", "comprehensive"], default="standard", help="Audit logging level")
    
    args = parser.parse_args()
    
    # Load configuration file if provided
    config = {}
    if args.config:
        try:
            config = load_config(args.config)
            logger.info(f"Loaded configuration from {args.config}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            sys.exit(1)
    
    # Build processing options
    processing_options = ProcessingOptions.default()
    
    # Override with config file values
    if config.get("processing_options"):
        processing_options.update(config["processing_options"])
    
    # Override with command-line arguments
    # Authentication options
    if args.require_auth:
        processing_options["require_authentication"] = True
    
    # Document parsing options
    if args.extract_tables:
        processing_options["extract_tables"] = True
    if args.extract_images:
        processing_options["extract_images"] = True
    if args.perform_ocr:
        processing_options["perform_ocr"] = True
    if args.no_chunking:
        processing_options["chunk_documents"] = False
    
    # Metadata options
    if args.scrub_metadata:
        processing_options["scrub_metadata"] = True
    if args.scrub_fields:
        processing_options["scrub_fields"] = [f.strip() for f in args.scrub_fields.split(",")]
    if args.scrub_mode:
        processing_options["scrub_mode"] = args.scrub_mode
    
    # Storage options
    if args.no_storage:
        processing_options["persist_to_database"] = False
    if args.encrypt:
        processing_options["encrypt_sensitive_data"] = True
    
    # Publication options
    if args.generate_preview:
        processing_options["generate_preview"] = True
    if args.index_for_search:
        processing_options["index_for_search"] = True
    
    # Advanced options
    processing_options["use_orchestrated_flow"] = not args.use_legacy_flow
    if args.audit_level:
        processing_options["audit_trail_level"] = args.audit_level
    
    # Process documents
    try:
        if args.batch:
            # Process a batch of documents
            file_paths = []
            if os.path.isdir(args.batch):
                # Get all files in the directory
                for root, _, files in os.walk(args.batch):
                    for file in files:
                        file_paths.append(os.path.join(root, file))
            elif os.path.isfile(args.batch):
                # Read file paths from the file
                with open(args.batch, 'r') as f:
                    file_paths = [line.strip() for line in f if line.strip()]
            else:
                logger.error(f"Invalid batch path: {args.batch}")
                sys.exit(1)
            
            # Filter for existing files
            file_paths = [path for path in file_paths if os.path.exists(path)]
            if not file_paths:
                logger.error("No valid files found for batch processing")
                sys.exit(1)
            
            logger.info(f"Processing batch of {len(file_paths)} documents")
            result = asyncio.run(process_batch(
                file_paths=file_paths,
                options=processing_options,
                user_id=args.user_id,
                base_output_dir=args.output_dir,
                log_directory=args.log_dir
            ))
            
        elif args.file_path:
            # Process a single document
            if not os.path.exists(args.file_path):
                logger.error(f"File not found: {args.file_path}")
                sys.exit(1)
            
            logger.info(f"Processing document: {args.file_path}")
            result = asyncio.run(process_document(
                file_path=args.file_path,
                document_id=args.document_id,
                options=processing_options,
                user_id=args.user_id,
                base_output_dir=args.output_dir,
                log_directory=args.log_dir
            ))
            
        else:
            logger.error("No input file or batch specified")
            parser.print_help()
            sys.exit(1)
        
        # Print summary
        print("\nProcessing Summary:")
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        logger.error(f"Error in document processing: {str(e)}")
        sys.exit(1)
    

if __name__ == "__main__":
    main()
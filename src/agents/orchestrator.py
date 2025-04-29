"""
Main Orchestrator for document unification system.

This orchestrator coordinates all specialized orchestrators and maintains global state.
It follows the standardized orchestration protocol for inter-orchestrator communication.
"""

import asyncio
import os
import uuid
import json
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union, Set
from pathlib import Path

# Specialized orchestrators
from .document_parser_orchestrator import DocumentParserOrchestrator
from .metadata_orchestrator import MetadataOrchestrator
from .storage_orchestrator import StorageOrchestrator
from .workflow_orchestrator import WorkflowOrchestrator
from .authentication_orchestrator import AuthenticationOrchestrator
from .audit_orchestrator import AuditOrchestrator
from .analytics_orchestrator import AnalyticsOrchestrator
from .publication_orchestrator import PublicationOrchestrator

# Import agents for backward compatibility with existing code
from .parser_agent import ParserAgent
from .chunking import ChunkingAgent
from .keywords import KeywordAgent
from .metadata_agent import MetadataAgent
from .validator_agent import ValidatorAgent
from src.storage.supabase_storage import StorageAgent

# Import the communication protocol
from src.utils.orchestrator_communication import (
    OrchestrationMessage,
    MessageType,
    OrchestrationStatus,
    OrchestratorAction
)
from src.utils.orchestrator_schema import RequestMetadata, ResponseMetadata
from src.utils.orchestrator_fallback import handling_exceptions
from src.utils.orchestrator_router import MessageRouter
from src.utils.orchestrator_logging import setup_logger

# Set up logger
logger = setup_logger("master_orchestrator")


class ProcessingOptions(Dict[str, Any]):
    """Container for document processing options."""
    
    @classmethod
    def default(cls) -> 'ProcessingOptions':
        """Create default processing options."""
        return cls({
            # Authentication options
            "require_authentication": False,
            "auth_level": "document_read",
            
            # Document parsing options
            "extract_tables": True,
            "extract_images": True,
            "perform_ocr": True,
            "detect_formatting": True,
            "chunk_documents": True,
            
            # Metadata options
            "scrub_metadata": True,
            "scrub_fields": ["author", "creator", "custom"],
            "scrub_mode": "redact",
            "extract_document_metadata": True,
            
            # Storage options
            "store_intermediate_results": True,
            "persist_to_database": True,
            "encrypt_sensitive_data": True,
            
            # Publication options
            "generate_preview": True,
            "index_for_search": True,
            
            # Compliance options
            "audit_trail_level": "comprehensive",  # basic, standard, comprehensive
            "compliance_frameworks": ["gdpr", "hipaa"],
            
            # Workflow options
            "workflow_template": "standard_document_processing",
            "parallelization": True,
            "priority": 5,  # 1-10 scale, 10 being highest
            
            # Fallback options
            "enable_graceful_fallbacks": True,
            "max_retries": 3,
            "retry_delay_seconds": 2
        })


class DocumentProcessState:
    """State container for tracking document processing."""
    
    def __init__(self, request_id: str, document_id: str, user_id: Optional[str] = None):
        """Initialize the document processing state."""
        self.request_id = request_id
        self.document_id = document_id
        self.user_id = user_id
        self.workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
        
        # Timestamps
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.updated_at = self.created_at
        self.completed_at = None
        
        # Processing status
        self.status = "initialized"
        self.current_stage = "initialization"
        self.progress = 0
        self.error = None
        
        # Processing results
        self.results = {}
        self.output_paths = {}
        self.metadata = {}
        
        # Orchestrator tracking
        self.orchestrator_history = []
        self.stage_durations = {}
    
    def update_status(self, status: str, stage: str, progress: int) -> None:
        """Update processing status."""
        self.status = status
        
        # Calculate stage duration if changing stages
        if self.current_stage != stage and self.current_stage:
            now = datetime.utcnow()
            last_stage = self.current_stage
            if last_stage not in self.stage_durations:
                self.stage_durations[last_stage] = 0
            
            # Get last stage update time
            last_updated = datetime.fromisoformat(self.updated_at.rstrip('Z'))
            duration = (now - last_updated).total_seconds()
            self.stage_durations[last_stage] += duration
        
        self.current_stage = stage
        self.progress = progress
        self.updated_at = datetime.utcnow().isoformat() + "Z"
        
        # If complete, set completion timestamp
        if status in ["completed", "failed"]:
            self.completed_at = self.updated_at
    
    def record_orchestrator_handoff(
        self,
        source: str,
        destination: str,
        message_type: str,
        result: str
    ) -> None:
        """Record an orchestrator handoff in the history."""
        handoff = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": source,
            "destination": destination,
            "message_type": message_type,
            "result": result
        }
        self.orchestrator_history.append(handoff)
    
    def add_result(self, stage: str, result: Dict[str, Any]) -> None:
        """Add processing result for a stage."""
        self.results[stage] = result
        self.updated_at = datetime.utcnow().isoformat() + "Z"
    
    def add_output_path(self, stage: str, path: str) -> None:
        """Add output file path for a stage."""
        self.output_paths[stage] = path
        self.updated_at = datetime.utcnow().isoformat() + "Z"
    
    def set_error(self, error_message: str, error_code: Optional[str] = None) -> None:
        """Set error information."""
        self.error = {
            "message": error_message,
            "code": error_code,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        self.updated_at = datetime.utcnow().isoformat() + "Z"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary representation."""
        return {
            "request_id": self.request_id,
            "document_id": self.document_id,
            "user_id": self.user_id,
            "workflow_id": self.workflow_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "current_stage": self.current_stage,
            "progress": self.progress,
            "error": self.error,
            "results": self.results,
            "output_paths": self.output_paths,
            "metadata": self.metadata,
            "orchestrator_history": self.orchestrator_history,
            "stage_durations": self.stage_durations
        }


class OrchestratorAgent:
    """
    Master Orchestrator Agent that coordinates specialized orchestrators 
    and maintains global state.
    
    Features:
    - Standardized communication protocol between orchestrators
    - Fault-tolerant execution with graceful fallbacks
    - Comprehensive audit logging and tracing
    - Support for parallel and sequential workflow execution
    - Backward compatibility with existing agent-based architecture
    """
    
    def __init__(
        self,
        base_output_dir: str = None,
        default_options: Optional[Dict[str, Any]] = None,
        log_directory: str = None
    ):
        """
        Initialize the master orchestrator with configuration options.
        
        Args:
            base_output_dir: Base directory for all outputs
            default_options: Default processing options
            log_directory: Directory for logging
        """
        self.orchestrator_id = f"master-orch-{uuid.uuid4().hex[:8]}"
        self.request_counter = 0
        
        # Set up directories
        self.base_output_dir = base_output_dir or os.environ.get(
            "BASE_OUTPUT_DIR", 
            os.path.join("output")
        )
        os.makedirs(self.base_output_dir, exist_ok=True)
        
        # Set up logging directory
        self.log_dir = log_directory or os.environ.get(
            "LOG_DIRECTORY", 
            os.path.join("logs")
        )
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Default options
        self.default_options = default_options or ProcessingOptions.default()
        
        # Initialize message router
        self.router = MessageRouter()
        
        # Active processing tracking
        self.active_processes = {}
        
        # Initialize specialized orchestrators
        self._initialize_orchestrators()
        
        # Register message handlers
        self._register_message_handlers()
        
        logger.info(f"Master Orchestrator {self.orchestrator_id} initialized")
        self.log_orchestrator_action(
            action=OrchestratorAction.INITIALIZE,
            target="master_orchestrator",
            status=OrchestrationStatus.SUCCESS,
            details="Master Orchestrator initialized with all specialized orchestrators"
        )
    
    def _initialize_orchestrators(self) -> None:
        """Initialize all specialized orchestrators."""
        # Document processing orchestrators
        self.document_parser = DocumentParserOrchestrator()
        self.metadata_orchestrator = MetadataOrchestrator(
            scrub_metadata=self.default_options.get("scrub_metadata", True),
            scrub_fields=self.default_options.get("scrub_fields", []),
            scrub_mode=self.default_options.get("scrub_mode", "redact")
        )
        self.storage_orchestrator = StorageOrchestrator()
        
        # Workflow and coordination orchestrators
        self.workflow_orchestrator = WorkflowOrchestrator()
        self.auth_orchestrator = AuthenticationOrchestrator()
        self.audit_orchestrator = AuditOrchestrator()
        
        # Analytics and publication orchestrators
        self.analytics_orchestrator = AnalyticsOrchestrator()
        self.publication_orchestrator = PublicationOrchestrator()
        
        # For backwards compatibility with existing code
        self.parser_agent = ParserAgent()
        self.chunking_agent = ChunkingAgent()
        self.keyword_agent = KeywordAgent()
        self.metadata_agent = MetadataAgent(
            scrub_metadata=self.default_options.get("scrub_metadata", True),
            scrub_fields=self.default_options.get("scrub_fields", []),
            scrub_mode=self.default_options.get("scrub_mode", "redact")
        )
        self.validator_agent = ValidatorAgent()
        self.storage_agent = StorageAgent()
    
    def _register_message_handlers(self) -> None:
        """Register message handlers for different message types."""
        self.router.register_handler(
            MessageType.DOCUMENT_PROCESS_REQUEST,
            self.handle_document_process_request
        )
        self.router.register_handler(
            MessageType.PROCESS_STATUS_REQUEST,
            self.handle_process_status_request
        )
        self.router.register_handler(
            MessageType.DOCUMENT_PARSE_RESPONSE,
            self.handle_parser_response
        )
        self.router.register_handler(
            MessageType.METADATA_PROCESS_RESPONSE,
            self.handle_metadata_response
        )
        self.router.register_handler(
            MessageType.STORAGE_RESPONSE,
            self.handle_storage_response
        )
    
    async def process_document(
        self,
        file_path: str,
        document_id: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process a document through the entire pipeline.
        This is the primary entry point for document processing.
        
        Args:
            file_path: Path to the document file to process
            document_id: Optional ID for the document
            options: Processing options that override defaults
            user_id: Optional user ID for authentication and audit
            
        Returns:
            Dict containing processing results and status
        """
        start_time = time.time()
        
        # Generate request ID and document ID if not provided
        request_id = f"req-{uuid.uuid4().hex[:12]}"
        document_id = document_id or f"doc-{uuid.uuid4().hex[:12]}"
        
        # Merge options with defaults
        process_options = {**self.default_options}
        if options:
            process_options.update(options)
        
        # Initialize processing state
        process_state = DocumentProcessState(
            request_id=request_id,
            document_id=document_id,
            user_id=user_id
        )
        self.active_processes[request_id] = process_state
        
        # Log processing start
        logger.info(f"Starting document processing for {file_path} with request ID {request_id}")
        self.log_orchestrator_action(
            action=OrchestratorAction.PROCESS_START,
            target=file_path,
            status=OrchestrationStatus.SUCCESS,
            details=f"Document processing started with request ID {request_id}",
            metadata={
                "request_id": request_id,
                "document_id": document_id,
                "user_id": user_id
            }
        )
        
        # Set up orchestration context
        context = {
            "request_id": request_id,
            "document_id": document_id,
            "workflow_id": process_state.workflow_id,
            "user_id": user_id,
            "file_path": file_path,
            "start_time": process_state.created_at,
            "process_options": process_options
        }
        
        # Process the document through orchestrated workflow
        try:
            # Check if we should use the new orchestrated flow or legacy flow
            if process_options.get("use_orchestrated_flow", True):
                result = await self._process_document_orchestrated(
                    file_path=file_path,
                    process_state=process_state,
                    context=context,
                    options=process_options
                )
            else:
                result = await self._process_document_legacy(
                    file_path=file_path,
                    process_state=process_state,
                    options=process_options
                )
            
            # Calculate processing time
            processing_time = time.time() - start_time
            result["processing_time_seconds"] = processing_time
            
            # Update process state
            process_state.add_result("final", result)
            process_state.update_status(
                status="completed",
                stage="completion",
                progress=100
            )
            
            # Log completion
            self.log_orchestrator_action(
                action=OrchestratorAction.PROCESS_COMPLETE,
                target=file_path,
                status=OrchestrationStatus.SUCCESS,
                details=f"Document processing completed in {processing_time:.2f} seconds",
                metadata={
                    "request_id": request_id,
                    "document_id": document_id,
                    "processing_time": processing_time
                }
            )
            
            return result
            
        except Exception as e:
            # Log error
            error_message = str(e)
            logger.error(f"Document processing failed: {error_message}")
            logger.error(traceback.format_exc())
            
            # Update process state
            process_state.update_status(
                status="failed",
                stage="error",
                progress=process_state.progress
            )
            process_state.set_error(error_message)
            
            # Log error
            self.log_orchestrator_action(
                action=OrchestratorAction.PROCESS_ERROR,
                target=file_path,
                status=OrchestrationStatus.ERROR,
                details=f"Document processing failed: {error_message}",
                metadata={
                    "request_id": request_id,
                    "document_id": document_id,
                    "error": error_message
                }
            )
            
            # Return error result
            return {
                "request_id": request_id,
                "document_id": document_id,
                "status": "error",
                "error": error_message,
                "processing_time_seconds": time.time() - start_time
            }
    
    async def _process_document_orchestrated(
        self,
        file_path: str,
        process_state: DocumentProcessState,
        context: Dict[str, Any],
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a document using the orchestrated flow with specialized orchestrators.
        
        Args:
            file_path: Path to the document file
            process_state: Current process state
            context: Orchestration context
            options: Processing options
            
        Returns:
            Dict containing processing results
        """
        request_id = context["request_id"]
        document_id = context["document_id"]
        
        # Initialize document state in workflow orchestrator
        process_state.update_status("in_progress", "workflow_initialization", 5)
        
        # Create metadata for request messages
        request_metadata = RequestMetadata(
            request_id=request_id,
            timestamp=datetime.utcnow().isoformat() + "Z",
            source=self.orchestrator_id
        )
        
        try:
            # Step 1: Authentication check if needed
            if options.get("require_authentication", False) and context.get("user_id"):
                process_state.update_status("in_progress", "authentication", 10)
                
                # Create authentication request message
                auth_message = OrchestrationMessage(
                    type=MessageType.AUTH_REQUEST,
                    payload={
                        "user_id": context["user_id"],
                        "resource_path": file_path,
                        "action": "read",
                        "auth_level": options.get("auth_level", "document_read")
                    },
                    metadata=request_metadata,
                    sender_id=self.orchestrator_id
                )
                
                # Send authentication request
                auth_response = await self.auth_orchestrator.handle_message(auth_message)
                
                # Process authentication response
                if auth_response.metadata.status != OrchestrationStatus.SUCCESS:
                    error_msg = auth_response.metadata.error_message or "Authentication failed"
                    logger.error(f"Authentication failed: {error_msg}")
                    process_state.set_error(error_msg, "AUTH_ERROR")
                    return {
                        "request_id": request_id,
                        "document_id": document_id,
                        "status": "error",
                        "stage": "authentication",
                        "error": error_msg
                    }
                
                # Record successful authentication
                process_state.record_orchestrator_handoff(
                    self.orchestrator_id,
                    self.auth_orchestrator.orchestrator_id,
                    "AUTH_REQUEST",
                    "success"
                )
                
                # Update context with authentication results
                auth_result = auth_response.payload
                context["auth_level"] = auth_result.get("auth_level")
                context["permissions"] = auth_result.get("permissions", [])
            
            # Step 2: Initialize workflow
            process_state.update_status("in_progress", "workflow_initialization", 15)
            
            # Create workflow initialization message
            workflow_message = OrchestrationMessage(
                type=MessageType.WORKFLOW_INIT_REQUEST,
                payload={
                    "workflow_template": options.get("workflow_template", "standard_document_processing"),
                    "context": context,
                    "priority": options.get("priority", 5)
                },
                metadata=request_metadata,
                sender_id=self.orchestrator_id
            )
            
            # Send workflow initialization request
            workflow_response = await self.workflow_orchestrator.handle_message(workflow_message)
            
            # Process workflow response
            if workflow_response.metadata.status != OrchestrationStatus.SUCCESS:
                error_msg = workflow_response.metadata.error_message or "Workflow initialization failed"
                logger.error(f"Workflow initialization failed: {error_msg}")
                process_state.set_error(error_msg, "WORKFLOW_ERROR")
                return {
                    "request_id": request_id,
                    "document_id": document_id,
                    "status": "error",
                    "stage": "workflow_initialization",
                    "error": error_msg
                }
            
            # Record successful workflow initialization
            process_state.record_orchestrator_handoff(
                self.orchestrator_id,
                self.workflow_orchestrator.orchestrator_id,
                "WORKFLOW_INIT_REQUEST",
                "success"
            )
            
            # Step 3: Document parsing
            process_state.update_status("in_progress", "document_parsing", 20)
            
            # Create document parsing message
            parse_message = OrchestrationMessage(
                type=MessageType.DOCUMENT_PARSE_REQUEST,
                payload={
                    "document_path": file_path,
                    "document_id": document_id,
                    "parse_options": {
                        "extract_tables": options.get("extract_tables", True),
                        "extract_images": options.get("extract_images", True),
                        "perform_ocr": options.get("perform_ocr", True),
                        "detect_formatting": options.get("detect_formatting", True),
                        "chunk_documents": options.get("chunk_documents", True)
                    }
                },
                metadata=request_metadata,
                sender_id=self.orchestrator_id
            )
            
            # Send document parsing request
            parse_response = await self.document_parser.handle_message(parse_message)
            
            # Process parsing response
            if parse_response.metadata.status != OrchestrationStatus.SUCCESS:
                error_msg = parse_response.metadata.error_message or "Document parsing failed"
                logger.error(f"Document parsing failed: {error_msg}")
                process_state.set_error(error_msg, "PARSE_ERROR")
                return {
                    "request_id": request_id,
                    "document_id": document_id,
                    "status": "error",
                    "stage": "document_parsing",
                    "error": error_msg
                }
            
            # Record successful parsing
            process_state.record_orchestrator_handoff(
                self.orchestrator_id,
                self.document_parser.orchestrator_id,
                "DOCUMENT_PARSE_REQUEST",
                "success"
            )
            
            # Update process state with parsing results
            parse_result = parse_response.payload
            process_state.add_result("parsing", parse_result)
            if "output_paths" in parse_result:
                for key, path in parse_result["output_paths"].items():
                    process_state.add_output_path(f"parsing_{key}", path)
            
            # Step 4: Metadata processing
            process_state.update_status("in_progress", "metadata_processing", 40)
            
            # Create metadata processing message
            metadata_message = OrchestrationMessage(
                type=MessageType.METADATA_PROCESS_REQUEST,
                payload={
                    "document_id": document_id,
                    "document_metadata": parse_result.get("metadata", {}),
                    "options": {
                        "scrub_metadata": options.get("scrub_metadata", True),
                        "scrub_fields": options.get("scrub_fields", []),
                        "scrub_mode": options.get("scrub_mode", "redact"),
                        "extract_document_metadata": options.get("extract_document_metadata", True)
                    }
                },
                metadata=request_metadata,
                sender_id=self.orchestrator_id
            )
            
            # Send metadata processing request
            metadata_response = await self.metadata_orchestrator.handle_message(metadata_message)
            
            # Process metadata response
            if metadata_response.metadata.status != OrchestrationStatus.SUCCESS:
                error_msg = metadata_response.metadata.error_message or "Metadata processing failed"
                logger.error(f"Metadata processing failed: {error_msg}")
                process_state.set_error(error_msg, "METADATA_ERROR")
                return {
                    "request_id": request_id,
                    "document_id": document_id,
                    "status": "error",
                    "stage": "metadata_processing",
                    "error": error_msg
                }
            
            # Record successful metadata processing
            process_state.record_orchestrator_handoff(
                self.orchestrator_id,
                self.metadata_orchestrator.orchestrator_id,
                "METADATA_PROCESS_REQUEST",
                "success"
            )
            
            # Update process state with metadata results
            metadata_result = metadata_response.payload
            process_state.add_result("metadata", metadata_result)
            process_state.metadata = metadata_result.get("processed_metadata", {})
            
            # Step 5: Storage
            process_state.update_status("in_progress", "storage", 70)
            
            # Create storage message
            storage_message = OrchestrationMessage(
                type=MessageType.STORAGE_REQUEST,
                payload={
                    "document_id": document_id,
                    "metadata": process_state.metadata,
                    "parsed_content": parse_result,
                    "output_paths": process_state.output_paths,
                    "options": {
                        "persist_to_database": options.get("persist_to_database", True),
                        "encrypt_sensitive_data": options.get("encrypt_sensitive_data", True)
                    }
                },
                metadata=request_metadata,
                sender_id=self.orchestrator_id
            )
            
            # Send storage request
            storage_response = await self.storage_orchestrator.handle_message(storage_message)
            
            # Process storage response
            if storage_response.metadata.status != OrchestrationStatus.SUCCESS:
                error_msg = storage_response.metadata.error_message or "Storage processing failed"
                logger.error(f"Storage processing failed: {error_msg}")
                process_state.set_error(error_msg, "STORAGE_ERROR")
                return {
                    "request_id": request_id,
                    "document_id": document_id,
                    "status": "error",
                    "stage": "storage",
                    "error": error_msg
                }
            
            # Record successful storage
            process_state.record_orchestrator_handoff(
                self.orchestrator_id,
                self.storage_orchestrator.orchestrator_id,
                "STORAGE_REQUEST",
                "success"
            )
            
            # Update process state with storage results
            storage_result = storage_response.payload
            process_state.add_result("storage", storage_result)
            
            # Step 6: Publication (optional)
            if options.get("generate_preview", True) or options.get("index_for_search", True):
                process_state.update_status("in_progress", "publication", 85)
                
                # Create publication message
                publication_message = OrchestrationMessage(
                    type=MessageType.PUBLICATION_REQUEST,
                    payload={
                        "document_id": document_id,
                        "metadata": process_state.metadata,
                        "storage_id": storage_result.get("storage_id"),
                        "options": {
                            "generate_preview": options.get("generate_preview", True),
                            "index_for_search": options.get("index_for_search", True)
                        }
                    },
                    metadata=request_metadata,
                    sender_id=self.orchestrator_id
                )
                
                # Send publication request
                publication_response = await self.publication_orchestrator.handle_message(publication_message)
                
                # Process publication response
                if publication_response.metadata.status != OrchestrationStatus.SUCCESS:
                    # Publication is optional, so log warning but continue
                    warning_msg = publication_response.metadata.error_message or "Publication processing warning"
                    logger.warning(f"Publication processing warning: {warning_msg}")
                else:
                    # Record successful publication
                    process_state.record_orchestrator_handoff(
                        self.orchestrator_id,
                        self.publication_orchestrator.orchestrator_id,
                        "PUBLICATION_REQUEST",
                        "success"
                    )
                    
                    # Update process state with publication results
                    publication_result = publication_response.payload
                    process_state.add_result("publication", publication_result)
            
            # Step 7: Log audit information
            process_state.update_status("in_progress", "audit_logging", 95)
            
            # Create audit message
            audit_message = OrchestrationMessage(
                type=MessageType.AUDIT_LOG_REQUEST,
                payload={
                    "document_id": document_id,
                    "request_id": request_id,
                    "user_id": context.get("user_id"),
                    "action": "document_processing",
                    "metadata": process_state.metadata,
                    "orchestrator_history": process_state.orchestrator_history,
                    "audit_level": options.get("audit_trail_level", "comprehensive")
                },
                metadata=request_metadata,
                sender_id=self.orchestrator_id
            )
            
            # Send audit request
            audit_response = await self.audit_orchestrator.handle_message(audit_message)
            
            # Process audit response (non-blocking, just log any issues)
            if audit_response.metadata.status != OrchestrationStatus.SUCCESS:
                logger.warning(f"Audit logging warning: {audit_response.metadata.error_message}")
            else:
                # Record successful audit
                process_state.record_orchestrator_handoff(
                    self.orchestrator_id,
                    self.audit_orchestrator.orchestrator_id,
                    "AUDIT_LOG_REQUEST",
                    "success"
                )
            
            # Step 8: Complete the workflow
            process_state.update_status("in_progress", "workflow_completion", 98)
            
            # Create workflow completion message
            completion_message = OrchestrationMessage(
                type=MessageType.WORKFLOW_COMPLETE_REQUEST,
                payload={
                    "workflow_id": context["workflow_id"],
                    "document_id": document_id,
                    "status": "success",
                    "results": {
                        "metadata": process_state.metadata,
                        "storage_id": storage_result.get("storage_id"),
                        "output_paths": process_state.output_paths
                    }
                },
                metadata=request_metadata,
                sender_id=self.orchestrator_id
            )
            
            # Send workflow completion request
            completion_response = await self.workflow_orchestrator.handle_message(completion_message)
            
            # Process completion response
            if completion_response.metadata.status != OrchestrationStatus.SUCCESS:
                logger.warning(f"Workflow completion warning: {completion_response.metadata.error_message}")
            else:
                # Record successful workflow completion
                process_state.record_orchestrator_handoff(
                    self.orchestrator_id,
                    self.workflow_orchestrator.orchestrator_id,
                    "WORKFLOW_COMPLETE_REQUEST",
                    "success"
                )
            
            # Build final result
            result = {
                "request_id": request_id,
                "document_id": document_id,
                "workflow_id": context["workflow_id"],
                "status": "success",
                "storage_id": storage_result.get("storage_id"),
                "output_paths": process_state.output_paths,
                "metadata": process_state.metadata
            }
            
            # Add statistics if available
            if parse_result.get("stats"):
                result["stats"] = parse_result["stats"]
            
            return result
            
        except Exception as e:
            # Log and re-raise the exception
            error_message = str(e)
            logger.error(f"Error in orchestrated document processing: {error_message}")
            logger.error(traceback.format_exc())
            raise
    
    async def _process_document_legacy(
        self,
        file_path: str,
        process_state: DocumentProcessState,
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a document using the legacy agent-based flow.
        
        Args:
            file_path: Path to the document file
            process_state: Current process state
            options: Processing options
            
        Returns:
            Dict containing processing results
        """
        request_id = process_state.request_id
        document_id = process_state.document_id
        
        try:
            # Step 1: Parse document
            process_state.update_status("in_progress", "parsing", 20)
            parsed_elements = self.parser_agent.parse_document(file_path)
            process_state.add_result("parsing", {"elements_count": len(parsed_elements)})
            
            # Step 2: Process metadata
            process_state.update_status("in_progress", "metadata", 40)
            document_metadata = {
                "filename": os.path.basename(file_path),
                "document_id": document_id
            }
            metadata_result = await self.metadata_agent.process(
                document_metadata, 
                scrub=options.get("scrub_metadata", True)
            )
            process_state.metadata = metadata_result.get("metadata", {})
            process_state.add_result("metadata", metadata_result)
            
            # Step 3: Chunk document
            process_state.update_status("in_progress", "chunking", 60)
            chunks = []
            if options.get("chunk_documents", True):
                chunking_result = self.chunking_agent.process(parsed_elements, document_id)
                chunks = chunking_result
                process_state.add_result("chunking", {"chunks_count": len(chunks)})
            
            # Step 4: Extract keywords (if needed)
            process_state.update_status("in_progress", "keywords", 70)
            keywords = []
            if options.get("extract_keywords", True):
                keywords_result = await self.keyword_agent.process(chunks)
                keywords = keywords_result.get("keywords", [])
                process_state.add_result("keywords", {"keywords_count": len(keywords)})
            
            # Step 5: Validate document (if needed)
            process_state.update_status("in_progress", "validation", 80)
            if options.get("validate_document", True):
                validation_result = await self.validator_agent.process_document(
                    document_id, parsed_elements, process_state.metadata
                )
                process_state.add_result("validation", validation_result)
            
            # Step 6: Store document
            process_state.update_status("in_progress", "storage", 90)
            if options.get("persist_to_database", True):
                storage_result = await self.storage_agent.store_document(
                    document_id=document_id,
                    metadata=process_state.metadata,
                    chunks=chunks,
                    keywords=keywords
                )
                process_state.add_result("storage", storage_result)
                
                # Save output path if available
                if "storage_path" in storage_result:
                    process_state.add_output_path("storage", storage_result["storage_path"])
            
            # Build final result
            result = {
                "request_id": request_id,
                "document_id": document_id,
                "status": "success",
                "elements_count": len(parsed_elements),
                "chunks_count": len(chunks),
                "keywords_count": len(keywords),
                "metadata": process_state.metadata
            }
            
            # Add storage ID if available
            if "storage" in process_state.results and "storage_id" in process_state.results["storage"]:
                result["storage_id"] = process_state.results["storage"]["storage_id"]
            
            return result
            
        except Exception as e:
            # Log and re-raise the exception
            error_message = str(e)
            logger.error(f"Error in legacy document processing: {error_message}")
            logger.error(traceback.format_exc())
            raise
    
    async def get_process_status(self, request_id: str) -> Dict[str, Any]:
        """
        Get the status of a document processing request.
        
        Args:
            request_id: ID of the processing request
            
        Returns:
            Dict containing current status information
        """
        if request_id in self.active_processes:
            process_state = self.active_processes[request_id]
            return {
                "request_id": request_id,
                "document_id": process_state.document_id,
                "status": process_state.status,
                "stage": process_state.current_stage,
                "progress": process_state.progress,
                "created_at": process_state.created_at,
                "updated_at": process_state.updated_at,
                "completed_at": process_state.completed_at,
                "error": process_state.error
            }
        else:
            return {
                "request_id": request_id,
                "status": "not_found",
                "error": "Request ID not found"
            }
    
    def get_all_processes(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status information for all active processes.
        
        Returns:
            Dict mapping request IDs to status information
        """
        return {
            request_id: {
                "request_id": request_id,
                "document_id": state.document_id,
                "status": state.status,
                "stage": state.current_stage,
                "progress": state.progress,
                "created_at": state.created_at,
                "updated_at": state.updated_at,
                "completed_at": state.completed_at
            }
            for request_id, state in self.active_processes.items()
        }
    
    def get_process_details(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific process.
        
        Args:
            request_id: ID of the processing request
            
        Returns:
            Dict containing detailed process information or None if not found
        """
        if request_id in self.active_processes:
            return self.active_processes[request_id].to_dict()
        else:
            return None
    
    def log_orchestrator_action(
        self,
        action: OrchestratorAction,
        target: str,
        status: OrchestrationStatus,
        details: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an orchestrator action to the action log.
        
        Args:
            action: Action performed by the orchestrator
            target: Target of the action
            status: Status of the action
            details: Details about the action
            metadata: Additional metadata
        """
        try:
            # Create log entry
            timestamp = datetime.utcnow().isoformat() + "Z"
            log_entry = {
                "timestamp": timestamp,
                "orchestrator_id": self.orchestrator_id,
                "action": action.value,
                "target": target,
                "status": status.value,
                "details": details
            }
            
            # Add metadata if provided
            if metadata:
                log_entry["metadata"] = self._filter_sensitive_data(metadata)
            
            # Log to console
            if status == OrchestrationStatus.ERROR:
                logger.error(f"{action.value}: {details}")
            else:
                logger.info(f"{action.value}: {details}")
            
            # Write to action log file
            log_path = os.path.join(self.log_dir, "orchestrator_actions.jsonl")
            with open(log_path, "a", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False)
                f.write("\n")
            
            # Send to audit orchestrator if available
            # This is done asynchronously without waiting for response
            asyncio.create_task(self._send_to_audit(log_entry))
            
        except Exception as e:
            logger.error(f"Error logging orchestrator action: {e}")
    
    def log_orchestrator_handoff(
        self,
        source: str,
        destination: str,
        message_type: str,
        context: Dict[str, Any],
        payload: Dict[str, Any],
        result: str
    ) -> None:
        """
        Log an orchestrator handoff to the handoff log.
        
        Args:
            source: Source orchestrator ID
            destination: Destination orchestrator ID
            message_type: Type of message being handed off
            context: Message context
            payload: Message payload
            result: Result of the handoff
        """
        try:
            # Create log entry
            timestamp = datetime.utcnow().isoformat() + "Z"
            
            # Filter sensitive data
            filtered_context = self._filter_sensitive_data(context)
            filtered_payload = self._filter_sensitive_data(payload)
            
            log_entry = {
                "timestamp": timestamp,
                "request_id": context.get("request_id", "unknown"),
                "source_orchestrator": source,
                "destination_orchestrator": destination,
                "message_type": message_type,
                "context": filtered_context,
                "payload_summary": self._summarize_payload(filtered_payload),
                "result": result
            }
            
            # Log to console
            if result == "error":
                logger.error(f"Handoff {message_type}: {source} → {destination} ({result})")
            else:
                logger.info(f"Handoff {message_type}: {source} → {destination} ({result})")
            
            # Write to handoff log file
            log_path = os.path.join(self.log_dir, "orchestrator_handoffs.jsonl")
            with open(log_path, "a", encoding="utf-8") as f:
                json.dump(log_entry, f, ensure_ascii=False)
                f.write("\n")
            
            # Update process state if applicable
            request_id = context.get("request_id")
            if request_id in self.active_processes:
                self.active_processes[request_id].record_orchestrator_handoff(
                    source, destination, message_type, result
                )
                
        except Exception as e:
            logger.error(f"Error logging orchestrator handoff: {e}")
    
    def _summarize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a summarized version of a payload for logging.
        
        Args:
            payload: Original payload
            
        Returns:
            Summarized payload with large fields truncated
        """
        if not isinstance(payload, dict):
            return payload
            
        summary = {}
        for key, value in payload.items():
            if isinstance(value, dict):
                summary[key] = self._summarize_payload(value)
            elif isinstance(value, list):
                if len(value) > 10:
                    summary[key] = f"List with {len(value)} items"
                else:
                    summary[key] = value[:5]
            elif isinstance(value, str) and len(value) > 100:
                summary[key] = value[:97] + "..."
            else:
                summary[key] = value
                
        return summary
    
    def _filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter sensitive data from dictionaries before logging.
        
        Args:
            data: Input data to filter
            
        Returns:
            Filtered data with sensitive fields redacted
        """
        if not isinstance(data, dict):
            return data
            
        filtered = {}
        sensitive_keys = ["password", "token", "api_key", "secret", "credential", "private"]
        
        for key, value in data.items():
            if any(sk in key.lower() for sk in sensitive_keys):
                filtered[key] = "<redacted>"
            elif isinstance(value, dict):
                filtered[key] = self._filter_sensitive_data(value)
            elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                filtered[key] = [self._filter_sensitive_data(item) for item in value]
            else:
                filtered[key] = value
                
        return filtered
    
    async def _send_to_audit(self, log_entry: Dict[str, Any]) -> None:
        """
        Send a log entry to the audit orchestrator.
        
        Args:
            log_entry: Log entry to send
        """
        with handling_exceptions("Sending to audit orchestrator"):
            # Create an audit message
            audit_message = OrchestrationMessage(
                type=MessageType.AUDIT_LOG_REQUEST,
                payload={
                    "log_entry": log_entry,
                    "log_type": "orchestrator_action",
                    "audit_level": "standard"
                },
                metadata=RequestMetadata(
                    request_id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    source=self.orchestrator_id
                ),
                sender_id=self.orchestrator_id
            )
            
            # Send to audit orchestrator
            await self.audit_orchestrator.handle_message(audit_message)
    
    async def handle_document_process_request(
        self,
        message: OrchestrationMessage
    ) -> OrchestrationMessage:
        """
        Handle a document process request message.
        
        Args:
            message: Incoming message
            
        Returns:
            Response message
        """
        logger.info(f"Received document process request from {message.sender_id}")
        
        payload = message.payload
        file_path = payload.get("file_path")
        document_id = payload.get("document_id")
        options = payload.get("options", {})
        user_id = payload.get("user_id")
        
        # Validate required fields
        if not file_path:
            return OrchestrationMessage(
                type=MessageType.DOCUMENT_PROCESS_RESPONSE,
                payload={"error": "Missing required field: file_path"},
                metadata=ResponseMetadata(
                    request_id=message.metadata.request_id,
                    correlation_id=message.metadata.correlation_id,
                    status=OrchestrationStatus.ERROR,
                    error_message="Missing required field: file_path"
                ),
                sender_id=self.orchestrator_id
            )
        
        # Process the document
        try:
            result = await self.process_document(
                file_path=file_path,
                document_id=document_id,
                options=options,
                user_id=user_id
            )
            
            # Return success response
            return OrchestrationMessage(
                type=MessageType.DOCUMENT_PROCESS_RESPONSE,
                payload=result,
                metadata=ResponseMetadata(
                    request_id=message.metadata.request_id,
                    correlation_id=message.metadata.correlation_id,
                    status=OrchestrationStatus.SUCCESS
                ),
                sender_id=self.orchestrator_id
            )
            
        except Exception as e:
            # Return error response
            error_message = str(e)
            logger.error(f"Error processing document: {error_message}")
            
            return OrchestrationMessage(
                type=MessageType.DOCUMENT_PROCESS_RESPONSE,
                payload={"error": error_message},
                metadata=ResponseMetadata(
                    request_id=message.metadata.request_id,
                    correlation_id=message.metadata.correlation_id,
                    status=OrchestrationStatus.ERROR,
                    error_message=error_message
                ),
                sender_id=self.orchestrator_id
            )
    
    async def handle_process_status_request(
        self,
        message: OrchestrationMessage
    ) -> OrchestrationMessage:
        """
        Handle a process status request message.
        
        Args:
            message: Incoming message
            
        Returns:
            Response message
        """
        logger.info(f"Received process status request from {message.sender_id}")
        
        payload = message.payload
        request_id = payload.get("request_id")
        
        # Validate required fields
        if not request_id:
            return OrchestrationMessage(
                type=MessageType.PROCESS_STATUS_RESPONSE,
                payload={"error": "Missing required field: request_id"},
                metadata=ResponseMetadata(
                    request_id=message.metadata.request_id,
                    correlation_id=message.metadata.correlation_id,
                    status=OrchestrationStatus.ERROR,
                    error_message="Missing required field: request_id"
                ),
                sender_id=self.orchestrator_id
            )
        
        # Get process status
        status = await self.get_process_status(request_id)
        
        # Return response
        return OrchestrationMessage(
            type=MessageType.PROCESS_STATUS_RESPONSE,
            payload=status,
            metadata=ResponseMetadata(
                request_id=message.metadata.request_id,
                correlation_id=message.metadata.correlation_id,
                status=OrchestrationStatus.SUCCESS
            ),
            sender_id=self.orchestrator_id
        )
    
    async def handle_parser_response(
        self,
        message: OrchestrationMessage
    ) -> OrchestrationMessage:
        """
        Handle a document parser response message.
        
        Args:
            message: Incoming message
            
        Returns:
            Response message
        """
        logger.info(f"Received parser response from {message.sender_id}")
        
        # Update process state if applicable
        request_id = message.metadata.request_id
        if request_id in self.active_processes:
            process_state = self.active_processes[request_id]
            
            # Record orchestrator handoff
            process_state.record_orchestrator_handoff(
                message.sender_id,
                self.orchestrator_id,
                "DOCUMENT_PARSE_RESPONSE",
                "received"
            )
            
            # Update process state based on response
            if message.metadata.status == OrchestrationStatus.SUCCESS:
                # Add parsing result
                process_state.add_result("parsing", message.payload)
                process_state.update_status("in_progress", "parsing_complete", 40)
            else:
                # Set error
                process_state.set_error(
                    message.metadata.error_message or "Parser error",
                    "PARSER_ERROR"
                )
                process_state.update_status("failed", "parsing_error", process_state.progress)
        
        # Acknowledge receipt
        return OrchestrationMessage(
            type=MessageType.ACKNOWLEDGEMENT,
            payload={"status": "received"},
            metadata=ResponseMetadata(
                request_id=message.metadata.request_id,
                correlation_id=message.metadata.correlation_id,
                status=OrchestrationStatus.SUCCESS
            ),
            sender_id=self.orchestrator_id
        )
    
    async def handle_metadata_response(
        self,
        message: OrchestrationMessage
    ) -> OrchestrationMessage:
        """
        Handle a metadata processor response message.
        
        Args:
            message: Incoming message
            
        Returns:
            Response message
        """
        logger.info(f"Received metadata response from {message.sender_id}")
        
        # Update process state if applicable
        request_id = message.metadata.request_id
        if request_id in self.active_processes:
            process_state = self.active_processes[request_id]
            
            # Record orchestrator handoff
            process_state.record_orchestrator_handoff(
                message.sender_id,
                self.orchestrator_id,
                "METADATA_PROCESS_RESPONSE",
                "received"
            )
            
            # Update process state based on response
            if message.metadata.status == OrchestrationStatus.SUCCESS:
                # Add metadata result
                process_state.add_result("metadata", message.payload)
                process_state.metadata = message.payload.get("processed_metadata", {})
                process_state.update_status("in_progress", "metadata_complete", 60)
            else:
                # Set error
                process_state.set_error(
                    message.metadata.error_message or "Metadata error",
                    "METADATA_ERROR"
                )
                process_state.update_status("failed", "metadata_error", process_state.progress)
        
        # Acknowledge receipt
        return OrchestrationMessage(
            type=MessageType.ACKNOWLEDGEMENT,
            payload={"status": "received"},
            metadata=ResponseMetadata(
                request_id=message.metadata.request_id,
                correlation_id=message.metadata.correlation_id,
                status=OrchestrationStatus.SUCCESS
            ),
            sender_id=self.orchestrator_id
        )
    
    async def handle_storage_response(
        self,
        message: OrchestrationMessage
    ) -> OrchestrationMessage:
        """
        Handle a storage response message.
        
        Args:
            message: Incoming message
            
        Returns:
            Response message
        """
        logger.info(f"Received storage response from {message.sender_id}")
        
        # Update process state if applicable
        request_id = message.metadata.request_id
        if request_id in self.active_processes:
            process_state = self.active_processes[request_id]
            
            # Record orchestrator handoff
            process_state.record_orchestrator_handoff(
                message.sender_id,
                self.orchestrator_id,
                "STORAGE_RESPONSE",
                "received"
            )
            
            # Update process state based on response
            if message.metadata.status == OrchestrationStatus.SUCCESS:
                # Add storage result
                process_state.add_result("storage", message.payload)
                
                # Update output paths if available
                if "storage_path" in message.payload:
                    process_state.add_output_path("storage", message.payload["storage_path"])
                
                process_state.update_status("in_progress", "storage_complete", 85)
            else:
                # Set error
                process_state.set_error(
                    message.metadata.error_message or "Storage error",
                    "STORAGE_ERROR"
                )
                process_state.update_status("failed", "storage_error", process_state.progress)
        
        # Acknowledge receipt
        return OrchestrationMessage(
            type=MessageType.ACKNOWLEDGEMENT,
            payload={"status": "received"},
            metadata=ResponseMetadata(
                request_id=message.metadata.request_id,
                correlation_id=message.metadata.correlation_id,
                status=OrchestrationStatus.SUCCESS
            ),
            sender_id=self.orchestrator_id
        )
    
    async def handle_message(self, message: OrchestrationMessage) -> OrchestrationMessage:
        """
        Handle an incoming orchestration message.
        
        Args:
            message: Incoming message
            
        Returns:
            Response message
        """
        logger.info(f"Received message: {message.type} from {message.sender_id}")
        
        # Log the handoff
        self.log_orchestrator_handoff(
            source=message.sender_id,
            destination=self.orchestrator_id,
            message_type=message.type,
            context={"request_id": message.metadata.request_id},
            payload=message.payload,
            result="received"
        )
        
        # Route the message to the appropriate handler
        try:
            response = await self.router.route_message(message)
            
            # If no handler found, return error
            if not response:
                return OrchestrationMessage(
                    type=MessageType.ERROR,
                    payload={"error": f"No handler for message type {message.type}"},
                    metadata=ResponseMetadata(
                        request_id=message.metadata.request_id,
                        correlation_id=message.metadata.correlation_id,
                        status=OrchestrationStatus.ERROR,
                        error_message=f"No handler for message type {message.type}"
                    ),
                    sender_id=self.orchestrator_id
                )
            
            return response
            
        except Exception as e:
            # Return error response
            error_message = str(e)
            logger.error(f"Error handling message: {error_message}")
            logger.error(traceback.format_exc())
            
            return OrchestrationMessage(
                type=MessageType.ERROR,
                payload={"error": error_message},
                metadata=ResponseMetadata(
                    request_id=message.metadata.request_id,
                    correlation_id=message.metadata.correlation_id,
                    status=OrchestrationStatus.ERROR,
                    error_message=error_message
                ),
                sender_id=self.orchestrator_id
            )
    
    def prune_completed_processes(self, max_age_seconds: int = 3600) -> int:
        """
        Remove completed processes from memory that are older than max_age_seconds.
        
        Args:
            max_age_seconds: Maximum age in seconds for completed processes
            
        Returns:
            Number of processes pruned
        """
        now = datetime.utcnow()
        completed_requests = []
        
        # Find completed processes that are old enough to prune
        for request_id, state in self.active_processes.items():
            if state.status in ["completed", "failed"] and state.completed_at:
                completed_time = datetime.fromisoformat(state.completed_at.rstrip('Z'))
                age_seconds = (now - completed_time).total_seconds()
                
                if age_seconds > max_age_seconds:
                    completed_requests.append(request_id)
        
        # Remove completed processes
        for request_id in completed_requests:
            self.active_processes.pop(request_id, None)
        
        return len(completed_requests)
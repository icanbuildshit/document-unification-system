"""
Main orchestrator for document unification system.
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# Specialized orchestrators
from .document_parser_orchestrator import DocumentParserOrchestrator
from .metadata_orchestrator import MetadataOrchestrator
from .storage_orchestrator import StorageOrchestrator
from .workflow_orchestrator import WorkflowOrchestrator
from .authentication_orchestrator import AuthenticationOrchestrator
from .audit_orchestrator import AuditComplianceOrchestrator
from .analytics_orchestrator import AnalyticsOrchestrator
from .publication_orchestrator import PublicationOrchestrator

# Import agents for backward compatibility with existing code
from .parser_agent import ParsingAgent
from .chunking import ChunkingAgent
from .keywords import KeywordAgent
from .metadata_agent import MetadataAgent
from src.storage.supabase_storage import StorageAgent

# Import the new communication protocol
from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    MessageContext,
    MessagePriority,
    MessageType,
    ErrorCode
)
from src.utils.orchestrator_fallback import register_fallback_handlers
from src.utils.orchestrator_router import send_message, create_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrchestratorAgent:
    """
    Master Orchestrator Agent that coordinates specialized orchestrators and maintains global state.
    
    The OrchestratorAgent is responsible for:
    1. Receiving document processing requests
    2. Delegating tasks to specialized orchestrators
    3. Tracking workflow status and progress
    4. Logging orchestration actions and handoffs
    5. Reporting overall process status
    """
    
    def __init__(
        self,
        scrub_metadata: bool = False,
        scrub_fields: Optional[List[str]] = None,
        scrub_mode: str = "redact",
    ):
        """Initialize the master orchestrator with configuration options."""
        self.orchestrator_id = f"master-orch-{uuid.uuid4().hex[:8]}"
        self.request_counter = 0
        
        # Register fallback handlers for graceful error handling
        register_fallback_handlers()
        
        # Initialize specialized orchestrators
        self.document_parser = DocumentParserOrchestrator()
        self.metadata_orchestrator = MetadataOrchestrator(
            scrub_metadata=scrub_metadata,
            scrub_fields=scrub_fields,
            scrub_mode=scrub_mode
        )
        self.storage_orchestrator = StorageOrchestrator()
        self.workflow_orchestrator = WorkflowOrchestrator()
        self.auth_orchestrator = AuthenticationOrchestrator()
        self.audit_orchestrator = AuditComplianceOrchestrator()
        self.analytics_orchestrator = AnalyticsOrchestrator()
        self.publication_orchestrator = PublicationOrchestrator()
        
        # For backwards compatibility with existing code
        self.parser = ParsingAgent()
        self.chunking = ChunkingAgent()
        self.keyword = KeywordAgent()
        self.metadata = MetadataAgent(
            scrub_metadata=scrub_metadata,
            scrub_fields=scrub_fields,
            scrub_mode=scrub_mode
        )
        self.storage = StorageAgent()
        
        logger.info(f"Master Orchestrator {self.orchestrator_id} initialized.")
        self._log_action(
            action="initialization",
            target="master_orchestrator",
            result="success",
            rationale="Master Orchestrator initialized with all specialized orchestrators."
        )
    
    async def process_document(self, file_path: str, document_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a document through the entire pipeline using specialized orchestrators.
        
        Args:
            file_path: Path to the document file to process
            document_id: Optional ID for the document
            
        Returns:
            Dict containing processing results
        """
        # Generate request ID and document ID if not provided
        request_id = f"req-{self.request_counter}"
        self.request_counter += 1
        document_id = document_id or f"doc-{uuid.uuid4().hex[:8]}"
        
        # Log the start of document processing
        self._log_action(
            action="process_document_start",
            target=file_path,
            result="initiated",
            rationale=f"Starting document processing with request ID {request_id}",
            extra={"request_id": request_id, "document_id": document_id}
        )
        
        # For now, maintain backward compatibility with existing pipeline
        # TODO: Replace with specialized orchestrator calls
        try:
            # Step 1: Parse document
            parsed_result = await self.parser.parse_document(file_path)
            
            # Step 2: Process metadata
            metadata_result = await self.metadata.process_metadata(
                parsed_result["metadata"],
                document_id
            )
            
            # Step 3: Chunk document
            chunked_result = await self.chunking.chunk_document(
                parsed_result["content"],
                document_id
            )
            
            # Step 4: Extract keywords
            keyword_result = await self.keyword.extract_keywords(
                chunked_result["chunks"],
                document_id
            )
            
            # Step 5: Store document with chunks and keywords
            storage_result = await self.storage.store_document(
                document_id=document_id,
                metadata=metadata_result["metadata"],
                chunks=chunked_result["chunks"],
                keywords=keyword_result["keywords"]
            )
            
            # Log successful completion
            self._log_action(
                action="process_document_complete",
                target=file_path,
                result="success",
                rationale=f"Document processing completed for request {request_id}",
                extra={
                    "request_id": request_id,
                    "document_id": document_id,
                    "storage_id": storage_result.get("storage_id")
                }
            )
            
            # Return combined results
            return {
                "request_id": request_id,
                "document_id": document_id,
                "status": "success",
                "storage_id": storage_result.get("storage_id"),
                "metadata": metadata_result.get("metadata", {}),
                "chunks_count": len(chunked_result.get("chunks", [])),
                "keywords_count": len(keyword_result.get("keywords", []))
            }
            
        except Exception as e:
            # Log failure
            error_message = str(e)
            self._log_action(
                action="process_document_error",
                target=file_path,
                result="error",
                rationale=f"Document processing failed: {error_message}",
                extra={"request_id": request_id, "document_id": document_id, "error": error_message}
            )
            
            # Re-raise to inform caller
            raise
    
    async def process_document_orchestrated(self, file_path: str, document_id: Optional[str] = None, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a document using the specialized orchestration architecture.
        This method will gradually replace process_document as components are migrated.
        
        Args:
            file_path: Path to the document file to process
            document_id: Optional ID for the document
            user_id: Optional user ID for authentication and audit purposes
            
        Returns:
            Dict containing processing results
        """
        # Generate request ID and document ID if not provided
        request_id = f"req-{self.request_counter}"
        self.request_counter += 1
        document_id = document_id or f"doc-{uuid.uuid4().hex[:8]}"
        workflow_id = f"workflow-{uuid.uuid4().hex[:8]}"
        
        # Record start time for metrics
        start_time = datetime.utcnow()
        
        # Initialize context that will be passed between orchestrators
        context = {
            "request_id": request_id,
            "document_id": document_id,
            "workflow_id": workflow_id,
            "user_id": user_id,
            "file_path": file_path,
            "start_time": start_time.isoformat() + "Z"
        }
        
        # Log the start of document processing
        self._log_orchestrator_handoff(
            source="client",
            destination=self.orchestrator_id,
            handoff_type="document_process_request",
            context=context,
            payload={"file_path": file_path},
            result="received"
        )
        
        try:
            # Step 1: Authentication (if user_id provided)
            if user_id:
                auth_result = await self.auth_orchestrator.validate_access(
                    user_id=user_id,
                    resource_path=file_path,
                    action="read"
                )
                
                # Update context with authentication results
                context["auth_level"] = auth_result.get("auth_level", "none")
                context["permissions"] = auth_result.get("permissions", [])
                
                # Log auth handoff
                self._log_orchestrator_handoff(
                    source=self.orchestrator_id,
                    destination=self.auth_orchestrator.orchestrator_id,
                    handoff_type="authentication_request",
                    context=context,
                    payload={"auth_type": "user_validation", "resource": file_path},
                    result="success"
                )
            
            # Step 2: Initialize workflow
            workflow_result = await self.workflow_orchestrator.initialize_workflow(
                workflow_template="document_processing_standard",
                context=context
            )
            
            # Log workflow handoff
            self._log_orchestrator_handoff(
                source=self.orchestrator_id,
                destination=self.workflow_orchestrator.orchestrator_id,
                handoff_type="workflow_initiation",
                context=context,
                payload={"workflow_template": "document_processing_standard", "priority": 1},
                result="success"
            )
            
            # Step 3: Document parsing
            parsing_result = await self.document_parser.parse_document(
                document_path=file_path,
                document_id=document_id,
                parse_options={"extract_tables": True, "preserve_layout": True}
            )
            
            # Log parsing handoff
            self._log_orchestrator_handoff(
                source=self.workflow_orchestrator.orchestrator_id,
                destination=self.document_parser.orchestrator_id,
                handoff_type="document_parse_request",
                context=context,
                payload={
                    "document_path": file_path,
                    "parse_options": {"extract_tables": True, "preserve_layout": True}
                },
                result="success"
            )
            
            # TODO: Implement remainder of orchestrated workflow
            # Step 4: Metadata processing
            # Step 5: Storage
            # Step 6: Publication
            
            # For now, return placeholder result
            return {
                "request_id": request_id,
                "document_id": document_id,
                "workflow_id": workflow_id,
                "status": "initiated",
                "message": "Document processing workflow initiated through specialized orchestrators"
            }
            
        except Exception as e:
            # Log failure
            error_message = str(e)
            self._log_action(
                action="process_document_orchestrated_error",
                target=file_path,
                result="error",
                rationale=f"Orchestrated document processing failed: {error_message}",
                extra={"request_id": request_id, "document_id": document_id, "error": error_message}
            )
            
            # Re-raise to inform caller
            raise
    
    def _log_action(self, action: str, target: str, result: str, rationale: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log an orchestrator action to the audit log."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        log_entry = {
            "timestamp": timestamp,
            "orchestrator_id": self.orchestrator_id,
            "action": action,
            "target": target,
            "result": result,
            "rationale": rationale
        }
        
        if extra:
            log_entry.update(extra)
        
        # Log to console for now
        logger.info(f"ORCHESTRATOR ACTION: {log_entry}")
        
        # TODO: Implement proper audit logging via AuditOrchestrator
    
    def _log_orchestrator_handoff(
        self,
        source: str,
        destination: str,
        handoff_type: str,
        context: Dict[str, Any],
        payload: Dict[str, Any],
        result: str
    ) -> None:
        """Log an orchestrator handoff to the orchestrator handoff log."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Filter sensitive data from context and payload
        filtered_context = self._filter_sensitive_data(context)
        filtered_payload = self._filter_sensitive_data(payload)
        
        log_entry = {
            "timestamp": timestamp,
            "request_id": context.get("request_id", "unknown"),
            "source_orchestrator": source,
            "destination_orchestrator": destination,
            "handoff_type": handoff_type,
            "context": filtered_context,
            "payload": filtered_payload,
            "result": result
        }
        
        # Log to console for now
        logger.info(f"ORCHESTRATOR HANDOFF: {log_entry}")
        
        # TODO: Implement proper handoff logging via AuditOrchestrator
        # Write to orchestrator_handoff.jsonl
        log_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "orchestrator_handoff.jsonl")
        
        try:
            import json
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write to orchestrator handoff log: {e}")
    
    def _filter_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Filter sensitive data from dictionaries before logging."""
        if not isinstance(data, dict):
            return data
            
        filtered = {}
        sensitive_keys = ["password", "token", "api_key", "secret", "credential"]
        
        for key, value in data.items():
            if any(sk in key.lower() for sk in sensitive_keys):
                filtered[key] = "<redacted>"
            elif isinstance(value, dict):
                filtered[key] = self._filter_sensitive_data(value)
            else:
                filtered[key] = value
                
        return filtered 
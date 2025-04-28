"""
Graceful fallback mechanisms for orchestrator error handling.

This module provides fallback handlers for various error scenarios to ensure
that the orchestration system can gracefully degrade rather than fail completely.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    ErrorCode,
    MessageType
)

logger = logging.getLogger(__name__)

def default_fallback_handler(message: OrchestrationMessage) -> OrchestrationMessage:
    """
    Default fallback handler for all orchestrators.
    
    This handler is used when an orchestrator is unavailable or returns an error.
    It provides a graceful degradation response rather than complete failure.
    
    Args:
        message: Original message that couldn't be processed
        
    Returns:
        Error response message with fallback information
    """
    logger.warning(f"Using default fallback handler for message {message.request_id} to {message.destination}")
    
    # Create a response that acknowledges the error but provides some fallback behavior
    return OrchestrationMessage(
        request_id=str(uuid.uuid4()),
        message_type=MessageType.ERROR,
        origin="fallback-handler",
        destination=message.origin,
        task=message.task,
        response_to=message.request_id,
        error=f"Original destination {message.destination} unavailable. Using fallback handler.",
        error_code=ErrorCode.ORCHESTRATOR_UNAVAILABLE,
        context=message.context,
        priority=message.priority,
        data={
            "fallback_used": True,
            "fallback_type": "default",
            "original_destination": message.destination,
            "original_task": message.task,
            "recovery_suggestion": "Retry later or check orchestrator status"
        }
    )

def document_parser_fallback(message: OrchestrationMessage) -> OrchestrationMessage:
    """
    Fallback handler for document parser orchestrator.
    
    Provides a degraded document parsing capability when the main parser is unavailable.
    
    Args:
        message: Original message that couldn't be processed
        
    Returns:
        Response message with minimal parsed document data
    """
    logger.warning(f"Using document parser fallback for message {message.request_id}")
    
    # Extract document path from parameters if available
    document_path = message.params.get("document_path", "unknown")
    
    # Create a minimal document structure as fallback
    fallback_data = {
        "fallback_used": True,
        "document_path": document_path,
        "content": "Document content could not be fully parsed. Using fallback parser.",
        "metadata": {
            "title": document_path.split("/")[-1] if "/" in document_path else document_path,
            "fallback_generated": True,
            "parse_status": "limited"
        },
        "parsed_components": [],
        "recovery_suggestion": "Retry with the main parser when available"
    }
    
    return OrchestrationMessage(
        request_id=str(uuid.uuid4()),
        message_type=MessageType.RESPONSE,
        origin="fallback-parser",
        destination=message.origin,
        task=message.task,
        response_to=message.request_id,
        context=message.context,
        priority=message.priority,
        data=fallback_data
    )

def storage_fallback(message: OrchestrationMessage) -> OrchestrationMessage:
    """
    Fallback handler for storage orchestrator.
    
    Provides a temporary storage solution when the main storage is unavailable.
    
    Args:
        message: Original message that couldn't be processed
        
    Returns:
        Response message with temporary storage information
    """
    logger.warning(f"Using storage fallback for message {message.request_id}")
    
    # Extract document ID from context if available
    document_id = message.context.document_id or "unknown"
    
    # Create fallback storage information
    fallback_data = {
        "fallback_used": True,
        "storage_type": "temporary",
        "document_id": document_id,
        "temporary_path": f"fallback_storage/{document_id}_{uuid.uuid4().hex[:8]}",
        "expiration": "24 hours",
        "recovery_suggestion": "Move data to permanent storage when available"
    }
    
    return OrchestrationMessage(
        request_id=str(uuid.uuid4()),
        message_type=MessageType.RESPONSE,
        origin="fallback-storage",
        destination=message.origin,
        task=message.task,
        response_to=message.request_id,
        context=message.context,
        priority=message.priority,
        data=fallback_data
    )

def metadata_fallback(message: OrchestrationMessage) -> OrchestrationMessage:
    """
    Fallback handler for metadata orchestrator.
    
    Provides minimal metadata processing when the main metadata orchestrator is unavailable.
    
    Args:
        message: Original message that couldn't be processed
        
    Returns:
        Response message with basic metadata information
    """
    logger.warning(f"Using metadata fallback for message {message.request_id}")
    
    # Extract document ID and any metadata from context and params
    document_id = message.context.document_id or "unknown"
    metadata = message.params.get("metadata", {})
    
    # Create fallback metadata
    fallback_data = {
        "fallback_used": True,
        "document_id": document_id,
        "metadata": {
            "title": metadata.get("title", f"Document {document_id}"),
            "fallback_generated": True,
            "processing_status": "limited"
        },
        "recovery_suggestion": "Process with full metadata orchestrator when available"
    }
    
    return OrchestrationMessage(
        request_id=str(uuid.uuid4()),
        message_type=MessageType.RESPONSE,
        origin="fallback-metadata",
        destination=message.origin,
        task=message.task,
        response_to=message.request_id,
        context=message.context,
        priority=message.priority,
        data=fallback_data
    )

def register_fallback_handlers():
    """
    Register fallback handlers for all orchestrators.
    
    This function should be called during system initialization to set up
    fallback handlers for graceful degradation.
    """
    from src.utils.orchestrator_router import register_fallback_handler, register_global_fallback
    
    # Register specialized fallback handlers
    register_fallback_handler("document-parser-orchestrator", document_parser_fallback)
    register_fallback_handler("storage-orchestrator", storage_fallback)
    register_fallback_handler("metadata-orchestrator", metadata_fallback)
    
    # Register default fallback for others
    register_global_fallback(default_fallback_handler)
    
    logger.info("Registered fallback handlers for orchestrators") 
"""
Specialized logging utilities for orchestrator communications and handoffs.

This module provides utilities for logging orchestrator communications, 
handoffs, and operations with consistent formatting and sensitive data filtering.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Union

from src.utils.orchestrator_communication import OrchestrationMessage

logger = logging.getLogger(__name__)

# Fields that should be redacted in logs
DEFAULT_SENSITIVE_FIELDS = {
    "password", "token", "secret", "key", "auth", "credential", "security_question",
    "ssn", "social_security", "dob", "birth", "credit_card", "cvv", "pin"
}

class OrchestrationLogger:
    """
    Logger for orchestrator operations and communications.
    
    Provides utilities for logging orchestrator messages, handoffs,
    and actions with consistent formatting and sensitive data handling.
    """
    
    def __init__(self, log_dir: str = "logs", sensitive_fields: Optional[Set[str]] = None):
        """
        Initialize the orchestration logger.
        
        Args:
            log_dir: Directory for log files
            sensitive_fields: Set of field names to redact (adds to defaults if provided)
        """
        self.log_dir = log_dir
        self.sensitive_fields = DEFAULT_SENSITIVE_FIELDS.copy()
        
        if sensitive_fields:
            self.sensitive_fields.update(sensitive_fields)
        
        # Create log directory if it doesn't exist
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Create orchestrator logs directory
        self.orchestrator_log_dir = os.path.join(self.log_dir, "orchestrator")
        os.makedirs(self.orchestrator_log_dir, exist_ok=True)
    
    def _redact_sensitive_data(self, data: Any) -> Any:
        """
        Redact sensitive data from logs.
        
        Args:
            data: Data to redact sensitive fields from
            
        Returns:
            Redacted data
        """
        if isinstance(data, dict):
            return {
                k: "[REDACTED]" if any(sensitive in k.lower() for sensitive in self.sensitive_fields) else self._redact_sensitive_data(v)
                for k, v in data.items()
            }
        elif isinstance(data, list):
            return [self._redact_sensitive_data(item) for item in data]
        else:
            return data
    
    def log_message(self, message: OrchestrationMessage, direction: str) -> None:
        """
        Log an orchestration message.
        
        Args:
            message: OrchestrationMessage to log
            direction: Direction of the message ("SENT" or "RECEIVED")
        """
        # Get message as dict for logging
        message_dict = message.to_dict()
        
        # Redact sensitive data
        safe_message = self._redact_sensitive_data(message_dict)
        
        # Create log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": "orchestrator_message",
            "direction": direction,
            "request_id": message.request_id,
            "origin": message.origin,
            "destination": message.destination,
            "task": message.task,
            "message": safe_message
        }
        
        # Write to orchestrator_messages.jsonl
        message_log_path = os.path.join(self.orchestrator_log_dir, "orchestrator_messages.jsonl")
        with open(message_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Log to Python logger as well
        logger.info(f"Orchestration message {direction}: {message.origin} -> {message.destination}, Task: {message.task}, Request ID: {message.request_id}")
    
    def log_handoff(self, from_orchestrator: str, to_orchestrator: str, document_id: str, context: Dict[str, Any]) -> None:
        """
        Log an orchestrator handoff event.
        
        Args:
            from_orchestrator: ID of the source orchestrator
            to_orchestrator: ID of the target orchestrator
            document_id: ID of the document being handed off
            context: Handoff context
        """
        # Redact sensitive data
        safe_context = self._redact_sensitive_data(context)
        
        # Create log entry
        handoff_id = f"handoff-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{document_id[:8]}"
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": "orchestrator_handoff",
            "handoff_id": handoff_id,
            "from_orchestrator": from_orchestrator,
            "to_orchestrator": to_orchestrator,
            "document_id": document_id,
            "context": safe_context,
            "status": "initiated"
        }
        
        # Write to orchestrator_handoffs.jsonl
        handoff_log_path = os.path.join(self.orchestrator_log_dir, "orchestrator_handoffs.jsonl")
        with open(handoff_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Log to Python logger as well
        logger.info(f"Orchestrator handoff: {from_orchestrator} -> {to_orchestrator}, Document: {document_id}, Handoff ID: {handoff_id}")
        
        return handoff_id
    
    def log_handoff_complete(self, handoff_id: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Log completion of an orchestrator handoff.
        
        Args:
            handoff_id: ID of the handoff
            status: Status of the handoff ("completed" or "failed")
            details: Optional details about the handoff result
        """
        # Redact sensitive data in details
        safe_details = self._redact_sensitive_data(details or {})
        
        # Create log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": "orchestrator_handoff_complete",
            "handoff_id": handoff_id,
            "status": status,
            "details": safe_details
        }
        
        # Write to orchestrator_handoffs.jsonl
        handoff_log_path = os.path.join(self.orchestrator_log_dir, "orchestrator_handoffs.jsonl")
        with open(handoff_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Log to Python logger as well
        logger.info(f"Orchestrator handoff {handoff_id} {status}")
    
    def log_orchestrator_action(self, orchestrator_id: str, action: str, details: Dict[str, Any]) -> None:
        """
        Log an action taken by an orchestrator.
        
        Args:
            orchestrator_id: ID of the orchestrator
            action: Action being performed
            details: Details about the action
        """
        # Redact sensitive data
        safe_details = self._redact_sensitive_data(details)
        
        # Create log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "type": "orchestrator_action",
            "orchestrator_id": orchestrator_id,
            "action": action,
            "details": safe_details
        }
        
        # Write to orchestrator_actions.jsonl
        action_log_path = os.path.join(self.orchestrator_log_dir, "orchestrator_actions.jsonl")
        with open(action_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
        
        # Log to Python logger as well
        logger.info(f"Orchestrator action: {orchestrator_id} - {action}")

# Global logger instance for application-wide use
global_logger = OrchestrationLogger()

def log_message(message: OrchestrationMessage, direction: str) -> None:
    """
    Log an orchestration message using the global logger.
    
    Convenience function for logging messages with the global logger.
    
    Args:
        message: OrchestrationMessage to log
        direction: Direction of the message ("SENT" or "RECEIVED")
    """
    global_logger.log_message(message, direction)

def log_handoff(from_orchestrator: str, to_orchestrator: str, document_id: str, context: Dict[str, Any]) -> str:
    """
    Log an orchestrator handoff using the global logger.
    
    Convenience function for logging handoffs with the global logger.
    
    Args:
        from_orchestrator: ID of the source orchestrator
        to_orchestrator: ID of the target orchestrator
        document_id: ID of the document being handed off
        context: Handoff context
        
    Returns:
        Handoff ID
    """
    return global_logger.log_handoff(from_orchestrator, to_orchestrator, document_id, context)

def log_handoff_complete(handoff_id: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
    """
    Log completion of an orchestrator handoff using the global logger.
    
    Convenience function for logging handoff completion with the global logger.
    
    Args:
        handoff_id: ID of the handoff
        status: Status of the handoff ("completed" or "failed")
        details: Optional details about the handoff result
    """
    global_logger.log_handoff_complete(handoff_id, status, details)

def log_orchestrator_action(orchestrator_id: str, action: str, details: Dict[str, Any]) -> None:
    """
    Log an orchestrator action using the global logger.
    
    Convenience function for logging orchestrator actions with the global logger.
    
    Args:
        orchestrator_id: ID of the orchestrator
        action: Action being performed
        details: Details about the action
    """
    global_logger.log_orchestrator_action(orchestrator_id, action, details) 
"""
Message schema for orchestrator communication protocol.

This module defines the standard schema for messages exchanged between orchestrators,
including validation utilities and schema definitions.
"""

import enum
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, Tuple
from dataclasses import asdict, dataclass, field, fields

class MessagePriority(enum.Enum):
    """Priority levels for orchestration messages."""
    LOW = "low"
    NORMAL = "normal" 
    HIGH = "high"
    CRITICAL = "critical"

class MessageType(enum.Enum):
    """Types of orchestration messages."""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"
    HANDOFF = "handoff"

class ErrorCode(enum.Enum):
    """Standard error codes for orchestration messages."""
    VALIDATION_ERROR = "validation_error"
    TASK_NOT_SUPPORTED = "task_not_supported"
    HANDLER_NOT_FOUND = "handler_not_found"
    PROCESSING_ERROR = "processing_error"
    RESOURCE_NOT_FOUND = "resource_not_found"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    ORCHESTRATOR_UNAVAILABLE = "orchestrator_unavailable"
    TIMEOUT = "timeout"
    DEPENDENCY_ERROR = "dependency_error"
    STORAGE_ERROR = "storage_error"
    GENERAL_ERROR = "general_error"

@dataclass
class MessageContext:
    """
    Context information for orchestration messages.
    Provides tracking and correlation data across orchestrator boundaries.
    """
    document_id: Optional[str] = None
    user_id: Optional[str] = None
    workflow_id: Optional[str] = None
    handoff_id: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    is_handoff: bool = False
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return {k: v for k, v in asdict(self).items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MessageContext':
        """Create context from dictionary."""
        # Filter out unknown fields
        known_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered_data)

@dataclass
class OrchestrationMessage:
    """
    Standard message format for inter-orchestrator communication.
    """
    # Required fields
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message_type: MessageType
    origin: str
    destination: str
    task: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    # Optional fields with defaults
    priority: MessagePriority = MessagePriority.NORMAL
    params: Dict[str, Any] = field(default_factory=dict)
    context: MessageContext = field(default_factory=MessageContext)
    
    # Response and error fields
    response_to: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[ErrorCode] = None
    
    # Payload data
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary with enum values converted to strings."""
        result = {}
        for key, value in asdict(self).items():
            if isinstance(value, enum.Enum):
                result[key] = value.value
            elif isinstance(value, MessageContext):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrchestrationMessage':
        """Create message from dictionary."""
        # Handle enum conversions
        if "message_type" in data and not isinstance(data["message_type"], MessageType):
            data["message_type"] = MessageType(data["message_type"])
        
        if "priority" in data and not isinstance(data["priority"], MessagePriority):
            data["priority"] = MessagePriority(data["priority"])
            
        if "error_code" in data and data["error_code"] and not isinstance(data["error_code"], ErrorCode):
            data["error_code"] = ErrorCode(data["error_code"])
            
        # Handle context conversion
        if "context" in data and not isinstance(data["context"], MessageContext):
            data["context"] = MessageContext.from_dict(data["context"])
            
        return cls(**data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'OrchestrationMessage':
        """Create message from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def create_response(self, data: Any = None) -> 'OrchestrationMessage':
        """
        Create a response message to this message.
        
        Args:
            data: Data to include in the response
            
        Returns:
            Response message
        """
        return OrchestrationMessage(
            message_type=MessageType.RESPONSE,
            origin=self.destination,
            destination=self.origin,
            task=self.task,
            response_to=self.request_id,
            context=self.context,
            data=data
        )
    
    def create_error_response(self, error: str, error_code: ErrorCode) -> 'OrchestrationMessage':
        """
        Create an error response message to this message.
        
        Args:
            error: Error message
            error_code: Error code
            
        Returns:
            Error response message
        """
        return OrchestrationMessage(
            message_type=MessageType.ERROR,
            origin=self.destination,
            destination=self.origin,
            task=self.task,
            response_to=self.request_id,
            context=self.context,
            error=error,
            error_code=error_code
        )

    def create_handoff_message(self, new_destination: str, new_task: str, 
                             new_params: Dict[str, Any] = None) -> 'OrchestrationMessage':
        """
        Create a handoff message to another orchestrator.
        
        Args:
            new_destination: New destination orchestrator ID
            new_task: New task for the destination
            new_params: New parameters for the task
            
        Returns:
            Handoff message
        """
        # Create new context with handoff flag set
        new_context = MessageContext(
            document_id=self.context.document_id,
            user_id=self.context.user_id,
            workflow_id=self.context.workflow_id,
            handoff_id=str(uuid.uuid4()),
            correlation_id=self.context.correlation_id,
            trace_id=self.context.trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=self.context.span_id,
            is_handoff=True,
            session_id=self.context.session_id,
            metadata=self.context.metadata.copy() if self.context.metadata else {}
        )
        
        return OrchestrationMessage(
            message_type=MessageType.HANDOFF,
            origin=self.destination,
            destination=new_destination,
            task=new_task,
            params=new_params or {},
            context=new_context
        )

def validate_message(message: OrchestrationMessage) -> Tuple[bool, Optional[str]]:
    """
    Validate an orchestration message against the schema.
    
    Args:
        message: The message to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check required fields
    required_fields = ["request_id", "message_type", "origin", "destination", "task", "timestamp"]
    
    for field in required_fields:
        if not getattr(message, field, None):
            return False, f"Missing required field: {field}"
    
    # Validate message_type
    if not isinstance(message.message_type, MessageType):
        return False, f"Invalid message_type: {message.message_type}"
    
    # Validate priority
    if not isinstance(message.priority, MessagePriority):
        return False, f"Invalid priority: {message.priority}"
    
    # Validate error_code if error is present
    if message.error and message.error_code is None:
        return False, "Error code must be provided when error message is present"
    
    # Validate response_to for response messages
    if message.message_type in [MessageType.RESPONSE, MessageType.ERROR] and not message.response_to:
        return False, "response_to must be provided for response and error messages"
    
    # Message is valid
    return True, None

def create_request_message(origin: str, destination: str, task: str, 
                         params: Dict[str, Any] = None, 
                         context: Dict[str, Any] = None,
                         priority: MessagePriority = MessagePriority.NORMAL) -> OrchestrationMessage:
    """
    Create a new request message.
    
    Args:
        origin: ID of the sender orchestrator
        destination: ID of the destination orchestrator
        task: Task to request from the destination
        params: Parameters for the task
        context: Context information to include
        priority: Message priority
        
    Returns:
        New request message
    """
    message_context = MessageContext(**context) if context else MessageContext()
    
    return OrchestrationMessage(
        message_type=MessageType.REQUEST,
        origin=origin,
        destination=destination,
        task=task,
        params=params or {},
        context=message_context,
        priority=priority
    ) 
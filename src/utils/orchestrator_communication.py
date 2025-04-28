"""
Orchestration communication protocol module.

Provides utilities and classes for standardized communication between orchestrators.
"""

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

logger = logging.getLogger(__name__)

@dataclass
class OrchestrationMessage:
    """
    Represents a message passed between orchestrators.
    """
    request_id: str
    origin: str
    destination: str
    task: str
    params: Dict[str, Any]
    context: Dict[str, Any]
    timestamp: float
    response_to: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary."""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrchestrationMessage':
        """Create message from dictionary."""
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
            request_id=str(uuid.uuid4()),
            origin=self.destination,
            destination=self.origin,
            task=self.task,
            params={},
            context=self.context,
            timestamp=time.time(),
            response_to=self.request_id,
            data=data
        )
    
    def create_error_response(self, error: str, error_code: str) -> 'OrchestrationMessage':
        """
        Create an error response message to this message.
        
        Args:
            error: Error message
            error_code: Error code
            
        Returns:
            Error response message
        """
        return OrchestrationMessage(
            request_id=str(uuid.uuid4()),
            origin=self.destination,
            destination=self.origin,
            task=self.task,
            params={},
            context=self.context,
            timestamp=time.time(),
            response_to=self.request_id,
            error=error,
            error_code=error_code,
            data=None
        )


class OrchestrationRouter:
    """
    Routes messages between orchestrators.
    
    This is a singleton class that maintains a registry of orchestrators and
    their message handlers.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OrchestrationRouter, cls).__new__(cls)
            cls._instance.handlers = {}
            cls._instance.orchestrators = {}
        return cls._instance
    
    def register_orchestrator(self, orchestrator_id: str, handler: Callable[[OrchestrationMessage], OrchestrationMessage]) -> None:
        """
        Register an orchestrator to receive messages.
        
        Args:
            orchestrator_id: Unique identifier for the orchestrator
            handler: Function to call when a message is sent to this orchestrator
        """
        self.orchestrators[orchestrator_id] = handler
        
        if orchestrator_id not in self.handlers:
            self.handlers[orchestrator_id] = {}
            
        logger.info(f"Registered orchestrator: {orchestrator_id}")
    
    def register_handler(self, orchestrator_id: str, task: str, handler: Callable[[OrchestrationMessage], Any]) -> None:
        """
        Register a handler for a specific task.
        
        Args:
            orchestrator_id: ID of the orchestrator
            task: Task name to handle
            handler: Function to call when this task is requested
        """
        if orchestrator_id not in self.handlers:
            self.handlers[orchestrator_id] = {}
            
        self.handlers[orchestrator_id][task] = handler
        logger.info(f"Registered handler for task '{task}' on orchestrator {orchestrator_id}")
    
    def send_message(self, message: OrchestrationMessage) -> OrchestrationMessage:
        """
        Send a message to an orchestrator.
        
        Args:
            message: Message to send
            
        Returns:
            Response message
        """
        destination = message.destination
        
        if destination not in self.orchestrators:
            error_message = f"Destination orchestrator not found: {destination}"
            logger.error(error_message)
            
            # Create error response
            return OrchestrationMessage(
                request_id=str(uuid.uuid4()),
                origin="router",
                destination=message.origin,
                task=message.task,
                params={},
                context=message.context,
                timestamp=time.time(),
                response_to=message.request_id,
                error=error_message,
                error_code="DESTINATION_NOT_FOUND",
                data=None
            )
        
        # Call the handler for the destination orchestrator
        handler = self.orchestrators[destination]
        return handler(message)


# Singleton router instance
_router = OrchestrationRouter()


def register_orchestrator(orchestrator_id: str, handler: Callable[[OrchestrationMessage], OrchestrationMessage]) -> None:
    """
    Register an orchestrator to receive messages.
    
    Args:
        orchestrator_id: Unique identifier for the orchestrator
        handler: Function to call when a message is sent to this orchestrator
    """
    _router.register_orchestrator(orchestrator_id, handler)


def register_handler(orchestrator_id: str, task: str, handler: Callable[[OrchestrationMessage], Any]) -> None:
    """
    Register a handler for a specific task.
    
    Args:
        orchestrator_id: ID of the orchestrator
        task: Task name to handle
        handler: Function to call when this task is requested
    """
    _router.register_handler(orchestrator_id, task, handler)


def create_message(origin: str, destination: str, task: str, params: Dict[str, Any] = None, context: Dict[str, Any] = None) -> OrchestrationMessage:
    """
    Create a new orchestration message.
    
    Args:
        origin: ID of the sender orchestrator
        destination: ID of the destination orchestrator
        task: Task to request from the destination
        params: Parameters for the task
        context: Context information to include
        
    Returns:
        New message
    """
    return OrchestrationMessage(
        request_id=str(uuid.uuid4()),
        origin=origin,
        destination=destination,
        task=task,
        params=params or {},
        context=context or {},
        timestamp=time.time(),
        response_to=None,
        error=None,
        error_code=None,
        data=None
    )


def send_message(message: OrchestrationMessage) -> OrchestrationMessage:
    """
    Send a message to an orchestrator.
    
    Args:
        message: Message to send
        
    Returns:
        Response message
    """
    return _router.send_message(message) 
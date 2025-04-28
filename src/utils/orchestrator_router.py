"""
Enhanced orchestration router with improved error handling and message validation.

This module provides a more robust implementation of the orchestration router with:
- Standardized message schema enforcement
- Advanced error handling and graceful fallbacks
- Support for message priorities and types
- Distributed tracing capabilities
"""

import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    MessageContext,
    MessagePriority,
    MessageType,
    ErrorCode,
    validate_message,
    create_request_message
)

logger = logging.getLogger(__name__)

# Type aliases for handler functions
MessageHandler = Callable[[OrchestrationMessage], OrchestrationMessage]
TaskHandler = Callable[[OrchestrationMessage], Any]

class OrchestrationRouter:
    """
    Enhanced router for orchestration messages with improved error handling.
    
    This router:
    1. Validates messages against the schema
    2. Routes messages to appropriate orchestrators
    3. Handles routing errors gracefully
    4. Supports message priorities
    5. Provides distributed tracing
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OrchestrationRouter, cls).__new__(cls)
            cls._instance.orchestrators: Dict[str, MessageHandler] = {}
            cls._instance.task_handlers: Dict[str, Dict[str, TaskHandler]] = {}
            cls._instance.fallback_handlers: Dict[str, MessageHandler] = {}
            cls._instance.global_fallback: Optional[MessageHandler] = None
        return cls._instance
    
    def register_orchestrator(self, orchestrator_id: str, handler: MessageHandler) -> None:
        """
        Register an orchestrator to receive messages.
        
        Args:
            orchestrator_id: Unique identifier for the orchestrator
            handler: Function to call when a message is sent to this orchestrator
        """
        self.orchestrators[orchestrator_id] = handler
        
        if orchestrator_id not in self.task_handlers:
            self.task_handlers[orchestrator_id] = {}
            
        logger.info(f"Registered orchestrator: {orchestrator_id}")
    
    def register_task_handler(self, orchestrator_id: str, task: str, handler: TaskHandler) -> None:
        """
        Register a handler for a specific task on an orchestrator.
        
        Args:
            orchestrator_id: ID of the orchestrator
            task: Task name to handle
            handler: Function to call when this task is requested
        """
        if orchestrator_id not in self.task_handlers:
            self.task_handlers[orchestrator_id] = {}
            
        self.task_handlers[orchestrator_id][task] = handler
        logger.info(f"Registered handler for task '{task}' on orchestrator {orchestrator_id}")
    
    def register_fallback_handler(self, orchestrator_id: str, handler: MessageHandler) -> None:
        """
        Register a fallback handler for an orchestrator.
        
        This handler will be called if the orchestrator is unavailable or if an error occurs.
        
        Args:
            orchestrator_id: ID of the orchestrator
            handler: Function to call when an error occurs with this orchestrator
        """
        self.fallback_handlers[orchestrator_id] = handler
        logger.info(f"Registered fallback handler for orchestrator {orchestrator_id}")
    
    def register_global_fallback(self, handler: MessageHandler) -> None:
        """
        Register a global fallback handler.
        
        This handler will be called if no specific fallback handler is registered for an orchestrator.
        
        Args:
            handler: Function to call when an error occurs with any orchestrator
        """
        self.global_fallback = handler
        logger.info("Registered global fallback handler")
    
    def send_message(self, message: OrchestrationMessage) -> OrchestrationMessage:
        """
        Send a message to an orchestrator.
        
        Args:
            message: Message to send
            
        Returns:
            Response message
        """
        # Validate the message
        is_valid, error_message = validate_message(message)
        if not is_valid:
            logger.error(f"Invalid message: {error_message}")
            return self._create_error_response(
                message,
                error_message,
                ErrorCode.VALIDATION_ERROR
            )
        
        destination = message.destination
        
        # Check if destination exists
        if destination not in self.orchestrators:
            logger.error(f"Destination orchestrator not found: {destination}")
            
            # Try fallback handler specific to this orchestrator
            if destination in self.fallback_handlers:
                logger.info(f"Using fallback handler for {destination}")
                return self.fallback_handlers[destination](message)
            
            # Try global fallback handler
            if self.global_fallback:
                logger.info("Using global fallback handler")
                return self.global_fallback(message)
            
            # Create error response
            return self._create_error_response(
                message,
                f"Destination orchestrator not found: {destination}",
                ErrorCode.ORCHESTRATOR_UNAVAILABLE
            )
        
        try:
            # Call the handler for the destination orchestrator
            handler = self.orchestrators[destination]
            start_time = time.time()
            
            # Log the message based on priority
            if message.priority == MessagePriority.HIGH or message.priority == MessagePriority.CRITICAL:
                logger.info(f"Processing {message.priority.value} priority message to {destination}: {message.task}")
            else:
                logger.debug(f"Processing message to {destination}: {message.task}")
            
            # Process the message
            response = handler(message)
            
            # Log processing time for performance monitoring
            processing_time = time.time() - start_time
            logger.debug(f"Message processing time: {processing_time:.6f}s")
            
            # Validate the response
            is_valid, error_message = validate_message(response)
            if not is_valid:
                logger.error(f"Invalid response from {destination}: {error_message}")
                return self._create_error_response(
                    message,
                    f"Invalid response from {destination}: {error_message}",
                    ErrorCode.VALIDATION_ERROR
                )
            
            return response
            
        except Exception as e:
            logger.exception(f"Error processing message to {destination}")
            
            # Try fallback handler specific to this orchestrator
            if destination in self.fallback_handlers:
                logger.info(f"Using fallback handler for {destination} after error")
                try:
                    return self.fallback_handlers[destination](message)
                except Exception as fallback_error:
                    logger.exception(f"Fallback handler for {destination} also failed")
            
            # Try global fallback handler
            if self.global_fallback:
                logger.info("Using global fallback handler after error")
                try:
                    return self.global_fallback(message)
                except Exception as global_fallback_error:
                    logger.exception("Global fallback handler also failed")
            
            # Create error response
            return self._create_error_response(
                message,
                f"Error processing message: {str(e)}",
                ErrorCode.PROCESSING_ERROR
            )
    
    def _create_error_response(self, message: OrchestrationMessage, error: str, error_code: ErrorCode) -> OrchestrationMessage:
        """
        Create an error response for a message.
        
        Args:
            message: Original message
            error: Error message
            error_code: Error code
            
        Returns:
            Error response message
        """
        return OrchestrationMessage(
            request_id=str(uuid.uuid4()),
            message_type=MessageType.ERROR,
            origin="router",
            destination=message.origin,
            task=message.task,
            response_to=message.request_id,
            error=error,
            error_code=error_code,
            context=message.context,
            priority=message.priority
        )

# Singleton router instance
_router = OrchestrationRouter()

def register_orchestrator(orchestrator_id: str, handler: MessageHandler) -> None:
    """
    Register an orchestrator to receive messages.
    
    Args:
        orchestrator_id: Unique identifier for the orchestrator
        handler: Function to call when a message is sent to this orchestrator
    """
    _router.register_orchestrator(orchestrator_id, handler)

def register_task_handler(orchestrator_id: str, task: str, handler: TaskHandler) -> None:
    """
    Register a handler for a specific task on an orchestrator.
    
    Args:
        orchestrator_id: ID of the orchestrator
        task: Task name to handle
        handler: Function to call when this task is requested
    """
    _router.register_task_handler(orchestrator_id, task, handler)

def register_fallback_handler(orchestrator_id: str, handler: MessageHandler) -> None:
    """
    Register a fallback handler for an orchestrator.
    
    Args:
        orchestrator_id: ID of the orchestrator
        handler: Function to call when an error occurs with this orchestrator
    """
    _router.register_fallback_handler(orchestrator_id, handler)

def register_global_fallback(handler: MessageHandler) -> None:
    """
    Register a global fallback handler.
    
    Args:
        handler: Function to call when an error occurs with any orchestrator
    """
    _router.register_global_fallback(handler)

def send_message(message: OrchestrationMessage) -> OrchestrationMessage:
    """
    Send a message to an orchestrator.
    
    Args:
        message: Message to send
        
    Returns:
        Response message
    """
    return _router.send_message(message)

def create_message(origin: str, destination: str, task: str, 
                 params: Dict[str, Any] = None, 
                 context: Dict[str, Any] = None,
                 priority: MessagePriority = MessagePriority.NORMAL) -> OrchestrationMessage:
    """
    Create a new orchestration message.
    
    Args:
        origin: ID of the sender orchestrator
        destination: ID of the destination orchestrator
        task: Task to request from the destination
        params: Parameters for the task
        context: Context information to include
        priority: Message priority
        
    Returns:
        New message
    """
    return create_request_message(
        origin=origin,
        destination=destination,
        task=task,
        params=params,
        context=context,
        priority=priority
    ) 
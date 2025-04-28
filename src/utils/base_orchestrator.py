"""
Base orchestrator class for standardized orchestrator implementation.

This module provides a base class for implementing orchestrators with
standardized communication, logging, and error handling.
"""

import json
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

# Import the new schema and router classes
from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    MessageContext,
    MessagePriority,
    MessageType,
    ErrorCode,
    create_request_message
)

from src.utils.orchestrator_router import (
    register_orchestrator,
    register_task_handler,
    register_fallback_handler,
    send_message,
    MessageHandler,
    TaskHandler
)

from src.utils.orchestrator_logging import (
    log_handoff,
    log_handoff_complete,
    log_message,
    log_orchestrator_action
)

logger = logging.getLogger(__name__)

class BaseOrchestrator(ABC):
    """
    Base class for all orchestrators in the system.
    
    Provides standard functionality for message handling, logging,
    error handling, and orchestrator communication using the enhanced
    message schema and communication protocol.
    """
    
    def __init__(self, orchestrator_id: str):
        """
        Initialize the base orchestrator.
        
        Args:
            orchestrator_id: Unique identifier for this orchestrator
        """
        self.orchestrator_id = orchestrator_id
        
        # Register this orchestrator for receiving messages
        register_orchestrator(orchestrator_id, self.handle_message)
        
        # Register task handlers for supported tasks
        for task in self.get_supported_tasks():
            handler = getattr(self, f"handle_{task}", None)
            if handler and callable(handler):
                register_task_handler(orchestrator_id, task, handler)
        
        # Log orchestrator initialization
        log_orchestrator_action(
            orchestrator_id=self.orchestrator_id,
            action="initialize",
            details={"supported_tasks": self.get_supported_tasks()}
        )
        
        logger.info(f"Orchestrator {orchestrator_id} initialized with tasks: {', '.join(self.get_supported_tasks())}")
    
    def handle_message(self, message: OrchestrationMessage) -> OrchestrationMessage:
        """
        Handle an incoming orchestration message.
        
        This is the main entry point for receiving messages from other orchestrators.
        
        Args:
            message: The incoming message to process
            
        Returns:
            Response message
        """
        # Log received message
        log_message(message, "RECEIVED")
        
        try:
            # Handle the message based on the task
            task = message.task
            
            if task in self.get_supported_tasks():
                # Try to get the handler method dynamically
                handler_method = getattr(self, f"handle_{task}", None)
                
                if handler_method and callable(handler_method):
                    # Log the action
                    log_orchestrator_action(
                        orchestrator_id=self.orchestrator_id,
                        action=f"handle_task_{task}",
                        details={
                            "request_id": message.request_id,
                            "params": message.params
                        }
                    )
                    
                    # Call the handler
                    result = handler_method(message)
                    
                    # Create response based on handler result
                    if isinstance(result, OrchestrationMessage):
                        # Handler returned a complete message
                        response = result
                    else:
                        # Handler returned data for a response
                        response = message.create_response(data=result)
                    
                    # Log the response
                    log_message(response, "SENT")
                    return response
                else:
                    # No handler method found for this task
                    error_message = f"No handler method found for task {task}"
                    logger.error(error_message)
                    
                    # Create error response
                    error_response = message.create_error_response(
                        error=error_message,
                        error_code=ErrorCode.HANDLER_NOT_FOUND
                    )
                    log_message(error_response, "SENT")
                    return error_response
            else:
                # Task not supported
                error_message = f"Task {task} not supported by {self.orchestrator_id}"
                logger.error(error_message)
                
                # Create error response
                error_response = message.create_error_response(
                    error=error_message,
                    error_code=ErrorCode.TASK_NOT_SUPPORTED
                )
                log_message(error_response, "SENT")
                return error_response
                
        except Exception as e:
            # Log the exception with full stack trace
            logger.exception(f"Error processing message {message.request_id} for task {message.task}")
            
            # Create a detailed error response with exception info
            error_message = f"Error processing message: {str(e)}"
            error_response = message.create_error_response(
                error=error_message,
                error_code=ErrorCode.PROCESSING_ERROR
            )
            
            # Log the error response
            log_message(error_response, "SENT")
            return error_response
    
    def send_message(
        self, 
        destination: str, 
        task: str, 
        params: Dict[str, Any] = None, 
        context: Dict[str, Any] = None,
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> OrchestrationMessage:
        """
        Send a message to another orchestrator.
        
        Args:
            destination: ID of the destination orchestrator
            task: Task to request from the destination
            params: Parameters for the task
            context: Context information to include
            priority: Message priority
            
        Returns:
            Response message from the destination
        """
        # Create message context
        message_context = context or {}
        
        # Create the message
        message = create_request_message(
            origin=self.orchestrator_id,
            destination=destination,
            task=task,
            params=params or {},
            context=message_context,
            priority=priority
        )
        
        # Log the message
        log_message(message, "SENT")
        
        # Send the message
        response = send_message(message)
        
        # Log the response
        log_message(response, "RECEIVED")
        
        return response
    
    def handoff_to_orchestrator(
        self, 
        to_orchestrator: str, 
        document_id: str, 
        task: str,
        params: Dict[str, Any] = None,
        context: Dict[str, Any] = None,
        priority: MessagePriority = MessagePriority.NORMAL
    ) -> Tuple[str, OrchestrationMessage]:
        """
        Perform a document handoff to another orchestrator.
        
        Creates a handoff log entry and sends a message to the destination orchestrator.
        
        Args:
            to_orchestrator: ID of the destination orchestrator
            document_id: ID of the document being handed off
            task: Task to request from the destination
            params: Parameters for the task
            context: Context information to include
            priority: Message priority
            
        Returns:
            Tuple of handoff_id and response message
        """
        # Combine params and context
        full_context = context or {}
        full_context["document_id"] = document_id
        
        # Generate handoff ID
        handoff_id = f"handoff-{uuid.uuid4().hex[:8]}"
        full_context["handoff_id"] = handoff_id
        full_context["is_handoff"] = True
        
        # Log the handoff
        log_handoff(
            from_orchestrator=self.orchestrator_id,
            to_orchestrator=to_orchestrator,
            document_id=document_id,
            context=full_context
        )
        
        # Send message to destination orchestrator
        response = self.send_message(
            destination=to_orchestrator,
            task=task,
            params=params or {},
            context=full_context,
            priority=priority
        )
        
        # Log handoff completion
        status = "completed" if not response.error else "failed"
        details = {"response_id": response.request_id}
        
        if response.error:
            details["error"] = response.error
            details["error_code"] = response.error_code.value if response.error_code else "unknown"
            
        log_handoff_complete(
            handoff_id=handoff_id,
            status=status,
            details=details
        )
        
        return handoff_id, response
    
    @abstractmethod
    def get_supported_tasks(self) -> List[str]:
        """
        Get the list of tasks supported by this orchestrator.
        
        Returns:
            List of task names
        """
        pass
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> None:
        """
        Handle an error that occurred during orchestration.
        
        Logs the error and any context information.
        
        Args:
            error: The exception that occurred
            context: Context information about when the error occurred
        """
        error_message = str(error)
        error_type = type(error).__name__
        
        # Log the error
        log_orchestrator_action(
            orchestrator_id=self.orchestrator_id,
            action="error",
            details={
                "error_type": error_type,
                "error_message": error_message,
                "context": context or {}
            }
        )
        
        # Log to Python logger as well
        logger.error(f"Error in orchestrator {self.orchestrator_id}: {error_type}: {error_message}")
        if context:
            logger.error(f"Error context: {json.dumps(context)}")
    
    def __del__(self):
        """
        Clean up when the orchestrator is destroyed.
        """
        try:
            # Log orchestrator shutdown
            log_orchestrator_action(
                orchestrator_id=self.orchestrator_id,
                action="shutdown",
                details={}
            )
            logger.info(f"Orchestrator {self.orchestrator_id} shut down")
        except:
            # Ignore errors during shutdown
            pass 
"""
Tests for the orchestrator communication protocol.

This file contains tests for the standardized orchestrator communication protocol,
including message schema validation and fallback handling.
"""

import unittest
import uuid
from unittest.mock import Mock, patch

from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    MessageContext,
    MessagePriority,
    MessageType,
    ErrorCode,
    validate_message,
    create_request_message
)

from src.utils.orchestrator_router import (
    OrchestrationRouter,
    register_orchestrator,
    register_fallback_handler,
    register_global_fallback,
    send_message
)

from src.utils.orchestrator_fallback import (
    default_fallback_handler,
    document_parser_fallback
)

class TestOrchestrationMessageSchema(unittest.TestCase):
    """Tests for the orchestration message schema and validation."""
    
    def test_create_request_message(self):
        """Test creating a request message with the message schema."""
        # Create a request message
        message = create_request_message(
            origin="test-orchestrator",
            destination="target-orchestrator",
            task="test_task",
            params={"param1": "value1", "param2": 42},
            context={"document_id": "doc-123", "user_id": "user-456"},
            priority=MessagePriority.HIGH
        )
        
        # Check message properties
        self.assertEqual(message.origin, "test-orchestrator")
        self.assertEqual(message.destination, "target-orchestrator")
        self.assertEqual(message.task, "test_task")
        self.assertEqual(message.params, {"param1": "value1", "param2": 42})
        self.assertEqual(message.context.document_id, "doc-123")
        self.assertEqual(message.context.user_id, "user-456")
        self.assertEqual(message.priority, MessagePriority.HIGH)
        self.assertEqual(message.message_type, MessageType.REQUEST)
        
        # Validate the message
        is_valid, error = validate_message(message)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_message_response(self):
        """Test creating a response message from a request message."""
        # Create a request message
        request = create_request_message(
            origin="test-orchestrator",
            destination="target-orchestrator",
            task="test_task"
        )
        
        # Create a response message
        response = request.create_response(data={"result": "success"})
        
        # Check response properties
        self.assertEqual(response.origin, "target-orchestrator")
        self.assertEqual(response.destination, "test-orchestrator")
        self.assertEqual(response.task, "test_task")
        self.assertEqual(response.response_to, request.request_id)
        self.assertEqual(response.data, {"result": "success"})
        self.assertEqual(response.message_type, MessageType.RESPONSE)
        
        # Validate the response
        is_valid, error = validate_message(response)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_message_error_response(self):
        """Test creating an error response message from a request message."""
        # Create a request message
        request = create_request_message(
            origin="test-orchestrator",
            destination="target-orchestrator",
            task="test_task"
        )
        
        # Create an error response message
        error_response = request.create_error_response(
            error="Test error message",
            error_code=ErrorCode.PROCESSING_ERROR
        )
        
        # Check error response properties
        self.assertEqual(error_response.origin, "target-orchestrator")
        self.assertEqual(error_response.destination, "test-orchestrator")
        self.assertEqual(error_response.task, "test_task")
        self.assertEqual(error_response.response_to, request.request_id)
        self.assertEqual(error_response.error, "Test error message")
        self.assertEqual(error_response.error_code, ErrorCode.PROCESSING_ERROR)
        self.assertEqual(error_response.message_type, MessageType.ERROR)
        
        # Validate the error response
        is_valid, error = validate_message(error_response)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_message_serialization(self):
        """Test serializing and deserializing messages."""
        # Create a message
        original_message = create_request_message(
            origin="test-orchestrator",
            destination="target-orchestrator",
            task="test_task",
            params={"param1": "value1", "param2": 42},
            context={"document_id": "doc-123", "user_id": "user-456"}
        )
        
        # Serialize to JSON and deserialize
        json_str = original_message.to_json()
        deserialized_message = OrchestrationMessage.from_json(json_str)
        
        # Check that deserialized message matches original
        self.assertEqual(deserialized_message.origin, original_message.origin)
        self.assertEqual(deserialized_message.destination, original_message.destination)
        self.assertEqual(deserialized_message.task, original_message.task)
        self.assertEqual(deserialized_message.params, original_message.params)
        self.assertEqual(deserialized_message.context.document_id, original_message.context.document_id)
        self.assertEqual(deserialized_message.context.user_id, original_message.context.user_id)
        self.assertEqual(deserialized_message.message_type, original_message.message_type)
        self.assertEqual(deserialized_message.request_id, original_message.request_id)

class TestOrchestrationRouter(unittest.TestCase):
    """Tests for the orchestration router with fallback handling."""
    
    def setUp(self):
        """Set up the test environment."""
        # Reset the router singleton for each test
        OrchestrationRouter._instance = None
        self.router = OrchestrationRouter()
    
    def test_register_and_call_orchestrator(self):
        """Test registering and calling an orchestrator."""
        # Create a mock handler
        mock_handler = Mock(return_value=OrchestrationMessage(
            request_id=str(uuid.uuid4()),
            message_type=MessageType.RESPONSE,
            origin="test-orchestrator",
            destination="caller",
            task="test_task",
            data={"result": "success"}
        ))
        
        # Register the mock handler
        register_orchestrator("test-orchestrator", mock_handler)
        
        # Create a message to send
        message = create_request_message(
            origin="caller",
            destination="test-orchestrator",
            task="test_task"
        )
        
        # Send the message
        response = send_message(message)
        
        # Check that the handler was called with the message
        mock_handler.assert_called_once_with(message)
        
        # Check the response
        self.assertEqual(response.origin, "test-orchestrator")
        self.assertEqual(response.destination, "caller")
        self.assertEqual(response.task, "test_task")
        self.assertEqual(response.data, {"result": "success"})
        self.assertEqual(response.message_type, MessageType.RESPONSE)
    
    def test_fallback_handler_for_missing_orchestrator(self):
        """Test using a fallback handler when the destination orchestrator is not found."""
        # Create a mock fallback handler
        mock_fallback = Mock(return_value=OrchestrationMessage(
            request_id=str(uuid.uuid4()),
            message_type=MessageType.RESPONSE,
            origin="fallback",
            destination="caller",
            task="test_task",
            data={"fallback": True}
        ))
        
        # Register the fallback handler
        register_fallback_handler("missing-orchestrator", mock_fallback)
        
        # Create a message to a missing orchestrator
        message = create_request_message(
            origin="caller",
            destination="missing-orchestrator",
            task="test_task"
        )
        
        # Send the message
        response = send_message(message)
        
        # Check that the fallback handler was called with the message
        mock_fallback.assert_called_once_with(message)
        
        # Check the response
        self.assertEqual(response.origin, "fallback")
        self.assertEqual(response.destination, "caller")
        self.assertEqual(response.task, "test_task")
        self.assertEqual(response.data, {"fallback": True})
    
    def test_global_fallback_handler(self):
        """Test using the global fallback handler when no specific fallback is registered."""
        # Create a mock global fallback handler
        mock_global_fallback = Mock(return_value=OrchestrationMessage(
            request_id=str(uuid.uuid4()),
            message_type=MessageType.RESPONSE,
            origin="global-fallback",
            destination="caller",
            task="test_task",
            data={"global_fallback": True}
        ))
        
        # Register the global fallback handler
        register_global_fallback(mock_global_fallback)
        
        # Create a message to a missing orchestrator with no specific fallback
        message = create_request_message(
            origin="caller",
            destination="another-missing-orchestrator",
            task="test_task"
        )
        
        # Send the message
        response = send_message(message)
        
        # Check that the global fallback handler was called with the message
        mock_global_fallback.assert_called_once_with(message)
        
        # Check the response
        self.assertEqual(response.origin, "global-fallback")
        self.assertEqual(response.destination, "caller")
        self.assertEqual(response.task, "test_task")
        self.assertEqual(response.data, {"global_fallback": True})

class TestFallbackHandlers(unittest.TestCase):
    """Tests for the predefined fallback handlers."""
    
    def test_default_fallback_handler(self):
        """Test the default fallback handler."""
        # Create a message
        message = create_request_message(
            origin="caller",
            destination="missing-orchestrator",
            task="test_task"
        )
        
        # Call the default fallback handler
        response = default_fallback_handler(message)
        
        # Check the response
        self.assertEqual(response.destination, "caller")
        self.assertEqual(response.task, "test_task")
        self.assertEqual(response.message_type, MessageType.ERROR)
        self.assertEqual(response.error_code, ErrorCode.ORCHESTRATOR_UNAVAILABLE)
        self.assertTrue("fallback_used" in response.data)
        self.assertEqual(response.data["fallback_used"], True)
    
    def test_document_parser_fallback(self):
        """Test the document parser fallback handler."""
        # Create a message with document path parameter
        message = create_request_message(
            origin="caller",
            destination="document-parser-orchestrator",
            task="parse_document",
            params={"document_path": "data/input/test.pdf"}
        )
        
        # Call the document parser fallback handler
        response = document_parser_fallback(message)
        
        # Check the response
        self.assertEqual(response.destination, "caller")
        self.assertEqual(response.task, "parse_document")
        self.assertEqual(response.message_type, MessageType.RESPONSE)
        self.assertTrue("fallback_used" in response.data)
        self.assertEqual(response.data["fallback_used"], True)
        self.assertEqual(response.data["document_path"], "data/input/test.pdf")
        self.assertTrue("parsed_components" in response.data)

if __name__ == "__main__":
    unittest.main() 
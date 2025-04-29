"""
Storage Orchestrator for coordinating document storage operations.
"""

import logging
import uuid
import os
import json
import hashlib
import shutil
import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Tuple
from pathlib import Path

from src.utils.base_orchestrator import BaseOrchestrator
from src.utils.orchestrator_schema import (
    OrchestrationMessage,
    MessageContext,
    MessagePriority,
    MessageType,
    ErrorCode
)

# Import supabase storage module if available
try:
    from src.storage.supabase_storage import SupabaseStorage
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

logger = logging.getLogger(__name__)

class StorageOrchestrator(BaseOrchestrator):
    """
    Orchestrates document storage operations across different backends.
    
    Responsible for:
    1. Managing document persistence across storage backends
    2. Handling chunking and retrieval operations
    3. Coordinating backup and recovery processes
    4. Maintaining storage optimization strategies
    5. Enforcing access controls for stored documents
    """
    
    def __init__(self):
        """Initialize the storage orchestrator."""
        self.orchestrator_id = "storage-orchestrator"
        super().__init__(self.orchestrator_id)
        
        # Initialize storage configuration
        self._init_storage_configuration()
        
        # Initialize storage backends
        self._init_storage_backends()
        
        # Initialize storage statistics
        self.storage_stats = {
            "total_documents": 0,
            "total_size_bytes": 0,
            "documents_by_type": {},
            "operations_count": {
                "store": 0,
                "retrieve": 0,
                "update": 0,
                "delete": 0,
                "backup": 0,
                "restore": 0
            },
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
        
        logger.info(f"Storage Orchestrator {self.orchestrator_id} initialized")
    
    def _init_storage_configuration(self):
        """Initialize storage configuration."""
        # Base directories
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self.data_dir = os.path.join(base_dir, "data")
        self.input_dir = os.path.join(self.data_dir, "input")
        self.output_dir = os.path.join(self.data_dir, "output")
        self.intermediate_dir = os.path.join(self.data_dir, "intermediate")
        self.backup_dir = os.path.join(base_dir, "backups")
        
        # Ensure directories exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.input_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.intermediate_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Storage tiers with configurations
        self.storage_tiers = {
            "standard": {
                "retention_days": 90,
                "encryption": "none",
                "redundancy": "single",
                "compression": "none"
            },
            "premium": {
                "retention_days": 365,
                "encryption": "aes-256",
                "redundancy": "dual",
                "compression": "gzip"
            },
            "archive": {
                "retention_days": 3650,
                "encryption": "aes-256",
                "redundancy": "triple",
                "compression": "high"
            }
        }
        
        # Default storage options
        self.default_storage_options = {
            "tier": "standard",
            "metadata": True,
            "versioning": True,
            "indexing": True,
            "max_versions": 3
        }
        
        # Storage backend priorities (ordered list)
        self.backend_priorities = ["local", "supabase", "remote"]
    
    def _init_storage_backends(self):
        """Initialize storage backends."""
        self.available_backends = {}
        
        # Always add local file system backend
        self.available_backends["local"] = {
            "type": "file",
            "root_dir": self.data_dir,
            "enabled": True,
            "priority": 1,
            "api": None  # No special API needed for local
        }
        
        # Add Supabase backend if available
        if SUPABASE_AVAILABLE:
            try:
                supabase_storage = SupabaseStorage()
                self.available_backends["supabase"] = {
                    "type": "supabase",
                    "enabled": True,
                    "priority": 2,
                    "api": supabase_storage
                }
                logger.info("Supabase storage backend initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase storage: {e}")
        
        # Load backend configuration from environment or config file
        # This would be extended with additional backends based on configuration
        
        logger.info(f"Initialized {len(self.available_backends)} storage backends")
    
    def get_supported_tasks(self) -> List[str]:
        """Get the list of tasks supported by this orchestrator."""
        return [
            "store_document",
            "retrieve_document",
            "update_document",
            "delete_document",
            "backup_document",
            "restore_document",
            "list_documents",
            "get_storage_status",
            "get_document_metadata",
            "chunk_document"
        ]
    
    def handle_store_document(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle storing a document with specified options.
        
        Args:
            message: Orchestration message with document storage parameters
            
        Returns:
            Document storage result
        """
        params = message.params
        
        # Check required parameters
        if "document_path" not in params:
            return message.create_error_response(
                error="Missing required parameter: document_path",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        document_path = params["document_path"]
        document_id = params.get("document_id", f"doc-{uuid.uuid4().hex[:12]}")
        storage_options = params.get("storage_options", self.default_storage_options.copy())
        
        # Check if document exists
        if not os.path.exists(document_path):
            return message.create_error_response(
                error=f"Document not found at path: {document_path}",
                error_code=ErrorCode.RESOURCE_NOT_FOUND
            )
        
        try:
            # Process and store the document
            result = self._store_document(document_path, document_id, storage_options)
            
            # Update storage statistics
            self._update_storage_stats("store", result)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error storing document: {str(e)}")
            return message.create_error_response(
                error=f"Error storing document: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_retrieve_document(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle retrieving a document from storage.
        
        Args:
            message: Orchestration message with document retrieval parameters
            
        Returns:
            Document retrieval result
        """
        params = message.params
        
        # Check required parameters
        if "document_id" not in params:
            return message.create_error_response(
                error="Missing required parameter: document_id",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        document_id = params["document_id"]
        version = params.get("version")
        output_path = params.get("output_path")
        include_content = params.get("include_content", False)
        
        try:
            # Retrieve the document
            result = self._retrieve_document(document_id, version, output_path, include_content)
            
            # Update storage statistics
            self._update_storage_stats("retrieve", result)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error retrieving document: {str(e)}")
            return message.create_error_response(
                error=f"Error retrieving document: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_update_document(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle updating a document in storage.
        
        Args:
            message: Orchestration message with document update parameters
            
        Returns:
            Document update result
        """
        params = message.params
        
        # Check required parameters
        required_params = ["document_id", "document_path"]
        for param in required_params:
            if param not in params:
                return message.create_error_response(
                    error=f"Missing required parameter: {param}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        document_id = params["document_id"]
        document_path = params["document_path"]
        storage_options = params.get("storage_options", {})
        create_version = params.get("create_version", True)
        
        # Check if document exists
        if not os.path.exists(document_path):
            return message.create_error_response(
                error=f"Update document not found at path: {document_path}",
                error_code=ErrorCode.RESOURCE_NOT_FOUND
            )
        
        try:
            # Update the document
            result = self._update_document(document_id, document_path, storage_options, create_version)
            
            # Update storage statistics
            self._update_storage_stats("update", result)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error updating document: {str(e)}")
            return message.create_error_response(
                error=f"Error updating document: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_delete_document(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle deleting a document from storage.
        
        Args:
            message: Orchestration message with document deletion parameters
            
        Returns:
            Document deletion result
        """
        params = message.params
        
        # Check required parameters
        if "document_id" not in params:
            return message.create_error_response(
                error="Missing required parameter: document_id",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        document_id = params["document_id"]
        delete_all_versions = params.get("delete_all_versions", False)
        soft_delete = params.get("soft_delete", True)
        
        try:
            # Delete the document
            result = self._delete_document(document_id, delete_all_versions, soft_delete)
            
            # Update storage statistics
            self._update_storage_stats("delete", result)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return message.create_error_response(
                error=f"Error deleting document: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_backup_document(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle creating a backup of a document.
        
        Args:
            message: Orchestration message with document backup parameters
            
        Returns:
            Document backup result
        """
        params = message.params
        
        # Check required parameters
        if "document_id" not in params:
            return message.create_error_response(
                error="Missing required parameter: document_id",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        document_id = params["document_id"]
        backup_options = params.get("backup_options", {})
        
        try:
            # Create a backup of the document
            result = self._backup_document(document_id, backup_options)
            
            # Update storage statistics
            self._update_storage_stats("backup", result)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error backing up document: {str(e)}")
            return message.create_error_response(
                error=f"Error backing up document: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_restore_document(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle restoring a document from backup.
        
        Args:
            message: Orchestration message with document restoration parameters
            
        Returns:
            Document restoration result
        """
        params = message.params
        
        # Check required parameters
        required_params = ["document_id", "backup_id"]
        for param in required_params:
            if param not in params:
                return message.create_error_response(
                    error=f"Missing required parameter: {param}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        document_id = params["document_id"]
        backup_id = params["backup_id"]
        restore_path = params.get("restore_path")
        
        try:
            # Restore the document from backup
            result = self._restore_document(document_id, backup_id, restore_path)
            
            # Update storage statistics
            self._update_storage_stats("restore", result)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error restoring document: {str(e)}")
            return message.create_error_response(
                error=f"Error restoring document: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_list_documents(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle listing documents in storage.
        
        Args:
            message: Orchestration message with document listing parameters
            
        Returns:
            Document listing result
        """
        params = message.params
        
        # Extract optional parameters
        filter_criteria = params.get("filter_criteria", {})
        limit = params.get("limit", 100)
        offset = params.get("offset", 0)
        sort_by = params.get("sort_by", "timestamp")
        sort_order = params.get("sort_order", "desc")
        
        try:
            # List documents
            result = self._list_documents(filter_criteria, limit, offset, sort_by, sort_order)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error listing documents: {str(e)}")
            return message.create_error_response(
                error=f"Error listing documents: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_get_storage_status(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle getting storage system status.
        
        Args:
            message: Orchestration message
            
        Returns:
            Storage status result
        """
        try:
            # Get storage status
            result = self._get_storage_status()
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error getting storage status: {str(e)}")
            return message.create_error_response(
                error=f"Error getting storage status: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_get_document_metadata(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle getting document metadata.
        
        Args:
            message: Orchestration message with document metadata parameters
            
        Returns:
            Document metadata result
        """
        params = message.params
        
        # Check required parameters
        if "document_id" not in params:
            return message.create_error_response(
                error="Missing required parameter: document_id",
                error_code=ErrorCode.VALIDATION_ERROR
            )
        
        document_id = params["document_id"]
        
        try:
            # Get document metadata
            result = self._get_document_metadata(document_id)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error getting document metadata: {str(e)}")
            return message.create_error_response(
                error=f"Error getting document metadata: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def handle_chunk_document(self, message: OrchestrationMessage) -> Dict[str, Any]:
        """
        Handle chunking a document for storage.
        
        Args:
            message: Orchestration message with document chunking parameters
            
        Returns:
            Document chunking result
        """
        params = message.params
        
        # Check required parameters
        required_params = ["document_id", "document_content"]
        for param in required_params:
            if param not in params:
                return message.create_error_response(
                    error=f"Missing required parameter: {param}",
                    error_code=ErrorCode.VALIDATION_ERROR
                )
        
        document_id = params["document_id"]
        document_content = params["document_content"]
        chunking_options = params.get("chunking_options", {})
        
        try:
            # Chunk the document
            result = self._chunk_document(document_id, document_content, chunking_options)
            
            return message.create_response(result)
        except Exception as e:
            logger.error(f"Error chunking document: {str(e)}")
            return message.create_error_response(
                error=f"Error chunking document: {str(e)}",
                error_code=ErrorCode.PROCESSING_ERROR
            )
    
    def _store_document(self, document_path: str, document_id: str, 
                     storage_options: Dict[str, Any]) -> Dict[str, Any]:
        """
        Store a document with specified options.
        
        Args:
            document_path: Path to the document file
            document_id: ID of the document
            storage_options: Dictionary of storage options
            
        Returns:
            Dictionary containing storage results
        """
        # Resolve absolute path
        document_path = os.path.abspath(document_path)
        
        # Get file information
        file_info = self._get_file_info(document_path)
        
        # Determine storage tier
        tier = storage_options.get("tier", self.default_storage_options["tier"])
        tier_config = self.storage_tiers.get(tier, self.storage_tiers["standard"])
        
        # Create storage metadata
        storage_metadata = {
            "original_filename": os.path.basename(document_path),
            "original_path": document_path,
            "content_type": file_info["content_type"],
            "size_bytes": file_info["size_bytes"],
            "checksum": file_info["checksum"],
            "created_at": datetime.utcnow().isoformat() + "Z",
            "storage_tier": tier,
            "storage_options": storage_options,
            "tier_config": tier_config,
            "version": "1.0"
        }
        
        # Determine target backends
        backends = self._select_storage_backends(storage_options)
        
        storage_locations = {}
        # Store in each backend
        for backend_name, backend in backends.items():
            storage_path = self._store_in_backend(backend_name, backend, document_path, document_id, storage_metadata)
            storage_locations[backend_name] = storage_path
        
        # Create index entry
        self._create_document_index_entry(document_id, storage_metadata, storage_locations)
        
        # Return storage result
        return {
            "document_id": document_id,
            "storage_id": f"storage-{uuid.uuid4().hex[:8]}",
            "storage_locations": storage_locations,
            "storage_timestamp": storage_metadata["created_at"],
            "storage_metadata": storage_metadata,
            "status": "success"
        }
    
    def _retrieve_document(self, document_id: str, version: Optional[str] = None, 
                        output_path: Optional[str] = None, 
                        include_content: bool = False) -> Dict[str, Any]:
        """
        Retrieve a document from storage.
        
        Args:
            document_id: ID of the document to retrieve
            version: Optional version to retrieve (if None, latest version)
            output_path: Optional path to copy the document to
            include_content: Whether to include the document content in the result
            
        Returns:
            Dictionary containing retrieved document information
        """
        # Get document index entry
        document_index = self._get_document_index_entry(document_id)
        
        if not document_index:
            raise ValueError(f"Document not found: {document_id}")
        
        # Handle versioning
        if version and version != document_index["metadata"]["version"]:
            versions = self._get_document_versions(document_id)
            if version not in versions:
                raise ValueError(f"Version not found: {version} for document {document_id}")
            
            # Load the specific version
            document_index = self._get_document_version(document_id, version)
        
        # Determine the best backend to retrieve from
        storage_locations = document_index["storage_locations"]
        retrieval_backend, retrieval_path = self._select_retrieval_backend(storage_locations)
        
        # Set output path if not provided
        if not output_path:
            output_path = os.path.join(self.output_dir, f"retrieved_{document_id}_{int(datetime.now().timestamp())}")
        
        # Retrieve the document
        retrieved_path = self._retrieve_from_backend(retrieval_backend, retrieval_path, output_path)
        
        result = {
            "document_id": document_id,
            "version": document_index["metadata"]["version"],
            "retrieved_path": retrieved_path,
            "metadata": document_index["metadata"],
            "retrieval_timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "success"
        }
        
        # Include content if requested
        if include_content and os.path.exists(retrieved_path):
            try:
                with open(retrieved_path, "rb") as f:
                    content = f.read()
                if len(content) > 1024 * 1024:  # Limit to 1MB
                    result["content_warning"] = "Content too large to include directly. Access via retrieved_path."
                else:
                    result["content"] = base64.b64encode(content).decode('utf-8')
                    result["content_encoding"] = "base64"
            except Exception as e:
                logger.warning(f"Failed to include content: {str(e)}")
                result["content_warning"] = f"Failed to include content: {str(e)}"
        
        return result
    
    def _update_document(self, document_id: str, document_path: str, 
                      storage_options: Dict[str, Any] = None, 
                      create_version: bool = True) -> Dict[str, Any]:
        """
        Update a document in storage.
        
        Args:
            document_id: ID of the document to update
            document_path: Path to the updated document file
            storage_options: Dictionary of storage options
            create_version: Whether to create a new version
            
        Returns:
            Dictionary containing update results
        """
        # Check if document exists
        document_index = self._get_document_index_entry(document_id)
        
        if not document_index:
            raise ValueError(f"Document not found for update: {document_id}")
        
        # Merge storage options with existing ones
        existing_options = document_index["metadata"]["storage_options"]
        merged_options = existing_options.copy()
        if storage_options:
            merged_options.update(storage_options)
        
        # If versioning is enabled, archive the current version
        if create_version and merged_options.get("versioning", True):
            self._archive_document_version(document_id, document_index)
        
        # Calculate the new version number
        current_version = document_index["metadata"]["version"]
        if create_version:
            version_parts = current_version.split(".")
            if len(version_parts) >= 2:
                minor_version = int(version_parts[1]) + 1
                new_version = f"{version_parts[0]}.{minor_version}"
            else:
                new_version = f"{current_version}.1"
        else:
            new_version = current_version
        
        # Store the new document
        # We reuse the store document logic, but override the document ID and version
        store_options = merged_options.copy()
        result = self._store_document(document_path, document_id, store_options)
        
        # Update the version in the result
        result["previous_version"] = current_version
        result["version"] = new_version
        result["storage_metadata"]["version"] = new_version
        result["is_update"] = True
        
        # Update the index entry with the new version
        self._update_document_index_entry(document_id, result["storage_metadata"], result["storage_locations"])
        
        return result
    
    def _delete_document(self, document_id: str, delete_all_versions: bool = False, 
                      soft_delete: bool = True) -> Dict[str, Any]:
        """
        Delete a document from storage.
        
        Args:
            document_id: ID of the document to delete
            delete_all_versions: Whether to delete all versions
            soft_delete: Whether to perform a soft delete (mark as deleted but retain data)
            
        Returns:
            Dictionary containing deletion results
        """
        # Check if document exists
        document_index = self._get_document_index_entry(document_id)
        
        if not document_index:
            raise ValueError(f"Document not found for deletion: {document_id}")
        
        # Get all versions if needed
        versions = []
        if delete_all_versions:
            versions = self._get_document_versions(document_id)
        
        deleted_locations = {}
        
        # Soft delete just updates metadata
        if soft_delete:
            # Mark the document as deleted in the index
            document_index["metadata"]["deleted"] = True
            document_index["metadata"]["deleted_at"] = datetime.utcnow().isoformat() + "Z"
            
            # Update the index entry
            self._update_document_index_entry(document_id, document_index["metadata"], document_index["storage_locations"])
            
            # Mark all versions as deleted if requested
            if delete_all_versions and versions:
                for version in versions:
                    version_index = self._get_document_version(document_id, version)
                    if version_index:
                        version_index["metadata"]["deleted"] = True
                        version_index["metadata"]["deleted_at"] = datetime.utcnow().isoformat() + "Z"
                        self._update_document_version(document_id, version, version_index["metadata"], version_index["storage_locations"])
            
            deleted_locations = document_index["storage_locations"]
        else:
            # Hard delete removes the files
            for backend_name, location in document_index["storage_locations"].items():
                if backend_name in self.available_backends:
                    backend = self.available_backends[backend_name]
                    deleted = self._delete_from_backend(backend_name, backend, location)
                    deleted_locations[backend_name] = deleted
            
            # Delete all versions if requested
            if delete_all_versions and versions:
                for version in versions:
                    version_index = self._get_document_version(document_id, version)
                    if version_index:
                        for backend_name, location in version_index["storage_locations"].items():
                            if backend_name in self.available_backends:
                                backend = self.available_backends[backend_name]
                                self._delete_from_backend(backend_name, backend, location)
                        
                        # Remove version index entry
                        self._delete_document_version_entry(document_id, version)
            
            # Remove the index entry
            self._delete_document_index_entry(document_id)
        
        return {
            "document_id": document_id,
            "deleted_versions": versions if delete_all_versions else [document_index["metadata"]["version"]],
            "deleted_locations": deleted_locations,
            "deletion_type": "soft" if soft_delete else "hard",
            "deletion_timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "success"
        }
    
    def _backup_document(self, document_id: str, backup_options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create a backup of a document.
        
        Args:
            document_id: ID of the document to backup
            backup_options: Dictionary of backup options
            
        Returns:
            Dictionary containing backup results
        """
        # Check if document exists
        document_index = self._get_document_index_entry(document_id)
        
        if not document_index:
            raise ValueError(f"Document not found for backup: {document_id}")
        
        # Default backup options
        default_backup_options = {
            "include_versions": False,
            "compression": True,
            "encryption": False
        }
        
        # Merge with provided options
        options = default_backup_options.copy()
        if backup_options:
            options.update(backup_options)
        
        # Generate backup ID and timestamp
        backup_id = f"backup-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        
        # Create backup directory
        backup_dir = os.path.join(self.backup_dir, document_id, timestamp)
        os.makedirs(backup_dir, exist_ok=True)
        
        # Backup the document
        backup_metadata = {
            "document_id": document_id,
            "backup_id": backup_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "options": options,
            "source_metadata": document_index["metadata"],
            "backed_up_files": []
        }
        
        # Backup current version
        version = document_index["metadata"]["version"]
        backed_up_files = []
        
        # Retrieve and store each file
        for backend_name, location in document_index["storage_locations"].items():
            if backend_name in self.available_backends:
                backend = self.available_backends[backend_name]
                backup_file_path = os.path.join(backup_dir, f"{backend_name}_{os.path.basename(location)}")
                retrieved = self._retrieve_from_backend(backend_name, location, backup_file_path)
                
                if retrieved:
                    backed_up_files.append({
                        "source_backend": backend_name,
                        "source_location": location,
                        "backup_path": backup_file_path,
                        "backup_success": True
                    })
        
        # Backup all versions if requested
        backed_up_versions = []
        if options["include_versions"]:
            versions = self._get_document_versions(document_id)
            for v in versions:
                if v != version:  # Skip the current version as it's already backed up
                    version_index = self._get_document_version(document_id, v)
                    if version_index:
                        version_backup_dir = os.path.join(backup_dir, f"version_{v}")
                        os.makedirs(version_backup_dir, exist_ok=True)
                        
                        version_files = []
                        for backend_name, location in version_index["storage_locations"].items():
                            if backend_name in self.available_backends:
                                backend = self.available_backends[backend_name]
                                backup_file_path = os.path.join(version_backup_dir, f"{backend_name}_{os.path.basename(location)}")
                                retrieved = self._retrieve_from_backend(backend_name, location, backup_file_path)
                                
                                if retrieved:
                                    version_files.append({
                                        "source_backend": backend_name,
                                        "source_location": location,
                                        "backup_path": backup_file_path,
                                        "backup_success": True
                                    })
                        
                        backed_up_versions.append({
                            "version": v,
                            "files": version_files
                        })
        
        # Update backup metadata
        backup_metadata["backed_up_files"] = backed_up_files
        backup_metadata["backed_up_versions"] = backed_up_versions
        
        # Write backup metadata
        with open(os.path.join(backup_dir, "backup_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(backup_metadata, f, indent=2)
        
        # Create a backup index entry
        self._create_backup_index_entry(document_id, backup_id, backup_metadata)
        
        # Log the backup
        logger.info(f"Created backup {backup_id} for document {document_id}")
        
        return {
            "document_id": document_id,
            "backup_id": backup_id,
            "backup_timestamp": backup_metadata["timestamp"],
            "backup_location": backup_dir,
            "backed_up_files": len(backed_up_files),
            "backed_up_versions": len(backed_up_versions),
            "status": "success"
        }
    
    def _restore_document(self, document_id: str, backup_id: str, 
                       restore_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Restore a document from backup.
        
        Args:
            document_id: ID of the document to restore
            backup_id: ID of the backup to restore from
            restore_path: Optional path to restore to
            
        Returns:
            Dictionary containing restoration results
        """
        # Get backup index entry
        backup_index = self._get_backup_index_entry(document_id, backup_id)
        
        if not backup_index:
            raise ValueError(f"Backup not found: {backup_id} for document {document_id}")
        
        # Determine restore path
        if not restore_path:
            restore_dir = os.path.join(self.output_dir, f"restored_{document_id}_{int(datetime.now().timestamp())}")
        else:
            restore_dir = restore_path
        
        os.makedirs(restore_dir, exist_ok=True)
        
        # Restore files
        restored_files = []
        for file_info in backup_index["backed_up_files"]:
            source_path = file_info["backup_path"]
            if os.path.exists(source_path):
                target_path = os.path.join(restore_dir, os.path.basename(source_path))
                shutil.copy2(source_path, target_path)
                restored_files.append({
                    "source_path": source_path,
                    "restore_path": target_path,
                    "restore_success": True
                })
            else:
                restored_files.append({
                    "source_path": source_path,
                    "restore_success": False,
                    "error": "Backup file not found"
                })
        
        # Restore versions if they were backed up
        restored_versions = []
        if "backed_up_versions" in backup_index:
            versions_dir = os.path.join(restore_dir, "versions")
            os.makedirs(versions_dir, exist_ok=True)
            
            for version_info in backup_index["backed_up_versions"]:
                version = version_info["version"]
                version_dir = os.path.join(versions_dir, f"version_{version}")
                os.makedirs(version_dir, exist_ok=True)
                
                version_files = []
                for file_info in version_info["files"]:
                    source_path = file_info["backup_path"]
                    if os.path.exists(source_path):
                        target_path = os.path.join(version_dir, os.path.basename(source_path))
                        shutil.copy2(source_path, target_path)
                        version_files.append({
                            "source_path": source_path,
                            "restore_path": target_path,
                            "restore_success": True
                        })
                    else:
                        version_files.append({
                            "source_path": source_path,
                            "restore_success": False,
                            "error": "Backup file not found"
                        })
                
                restored_versions.append({
                    "version": version,
                    "files": version_files
                })
        
        # Copy backup metadata
        shutil.copy2(
            os.path.join(os.path.dirname(backup_index["backed_up_files"][0]["backup_path"]), "backup_metadata.json"),
            os.path.join(restore_dir, "backup_metadata.json")
        )
        
        return {
            "document_id": document_id,
            "backup_id": backup_id,
            "restore_timestamp": datetime.utcnow().isoformat() + "Z",
            "restore_path": restore_dir,
            "restored_files": len(restored_files),
            "restored_versions": len(restored_versions),
            "status": "success"
        }
    
    def _list_documents(self, filter_criteria: Dict[str, Any] = None, 
                      limit: int = 100, offset: int = 0, 
                      sort_by: str = "timestamp", 
                      sort_order: str = "desc") -> Dict[str, Any]:
        """
        List documents in storage.
        
        Args:
            filter_criteria: Dictionary of filter criteria
            limit: Maximum number of documents to return
            offset: Number of documents to skip
            sort_by: Field to sort by
            sort_order: Sort order ("asc" or "desc")
            
        Returns:
            Dictionary containing document listing
        """
        # Get document index directory
        index_dir = os.path.join(self.data_dir, "index")
        
        # Default result
        result = {
            "documents": [],
            "count": 0,
            "total": 0,
            "limit": limit,
            "offset": offset,
            "filter_criteria": filter_criteria or {},
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Check if index directory exists
        if not os.path.exists(index_dir):
            return result
        
        # List all document index files
        index_files = [f for f in os.listdir(index_dir) if f.endswith(".json") and not f.startswith("backup_")]
        
        # Load document metadata from index files
        documents = []
        for index_file in index_files:
            try:
                with open(os.path.join(index_dir, index_file), "r", encoding="utf-8") as f:
                    document_index = json.load(f)
                
                # Apply filters if provided
                if filter_criteria:
                    if not self._matches_filter_criteria(document_index["metadata"], filter_criteria):
                        continue
                
                # Add to document list (minimal info)
                documents.append({
                    "document_id": document_index["document_id"],
                    "original_filename": document_index["metadata"]["original_filename"],
                    "content_type": document_index["metadata"]["content_type"],
                    "size_bytes": document_index["metadata"]["size_bytes"],
                    "created_at": document_index["metadata"]["created_at"],
                    "version": document_index["metadata"]["version"],
                    "storage_tier": document_index["metadata"]["storage_tier"],
                    "deleted": document_index["metadata"].get("deleted", False)
                })
            except Exception as e:
                logger.warning(f"Error loading document index {index_file}: {str(e)}")
        
        # Sort documents
        reverse = sort_order.lower() == "desc"
        if sort_by == "timestamp":
            sort_by = "created_at"
        
        documents.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)
        
        # Apply pagination
        paginated_documents = documents[offset:offset + limit]
        
        result["documents"] = paginated_documents
        result["count"] = len(paginated_documents)
        result["total"] = len(documents)
        
        return result
    
    def _get_storage_status(self) -> Dict[str, Any]:
        """
        Get status information about the storage system.
        
        Returns:
            Dictionary with storage status information
        """
        # Update statistics if needed
        self._refresh_storage_stats()
        
        # Get disk usage information
        disk_usage = self._get_disk_usage()
        
        # Get backend status
        backend_status = {}
        for backend_name, backend in self.available_backends.items():
            backend_status[backend_name] = {
                "type": backend["type"],
                "enabled": backend["enabled"],
                "priority": backend["priority"],
                "status": "healthy"  # Default status
            }
        
        return {
            "total_documents": self.storage_stats["total_documents"],
            "total_size_bytes": self.storage_stats["total_size_bytes"],
            "documents_by_type": self.storage_stats["documents_by_type"],
            "operations_count": self.storage_stats["operations_count"],
            "available_space_bytes": disk_usage["available"],
            "total_space_bytes": disk_usage["total"],
            "usage_percent": disk_usage["percent"],
            "storage_backends": backend_status,
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "status": "healthy"
        }
    
    def _get_document_metadata(self, document_id: str) -> Dict[str, Any]:
        """
        Get metadata for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            Dictionary containing document metadata
        """
        # Get document index entry
        document_index = self._get_document_index_entry(document_id)
        
        if not document_index:
            raise ValueError(f"Document not found: {document_id}")
        
        # Get versions if available
        versions = self._get_document_versions(document_id)
        
        # Return document metadata
        return {
            "document_id": document_id,
            "metadata": document_index["metadata"],
            "storage_locations": document_index["storage_locations"],
            "versions": versions,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    
    def _chunk_document(self, document_id: str, document_content: Union[str, Dict, List],
                      chunking_options: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Chunk a document for storage.
        
        Args:
            document_id: ID of the document
            document_content: Document content
            chunking_options: Dictionary of chunking options
            
        Returns:
            Dictionary containing chunking results
        """
        # Default chunking options
        default_chunking_options = {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "include_metadata": True
        }
        
        # Merge with provided options
        options = default_chunking_options.copy()
        if chunking_options:
            options.update(chunking_options)
        
        # Generate chunks
        chunks = []
        
        # Handle different content types
        if isinstance(document_content, str):
            # Simple text chunking
            chunk_size = options["chunk_size"]
            chunk_overlap = options["chunk_overlap"]
            
            # Split by chunks with overlap
            for i in range(0, len(document_content), chunk_size - chunk_overlap):
                chunk_text = document_content[i:i + chunk_size]
                chunk_id = f"chunk-{document_id}-{len(chunks)}"
                
                chunk = {
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "start_index": i,
                    "end_index": min(i + chunk_size, len(document_content)),
                    "metadata": {
                        "document_id": document_id,
                        "chunk_index": len(chunks),
                        "total_chunks": -1  # Will be updated later
                    }
                }
                
                chunks.append(chunk)
        elif isinstance(document_content, dict) or isinstance(document_content, list):
            # Convert to JSON string and chunk
            json_str = json.dumps(document_content)
            return self._chunk_document(document_id, json_str, chunking_options)
        else:
            raise ValueError(f"Unsupported document content type: {type(document_content)}")
        
        # Update total chunks in metadata
        for chunk in chunks:
            chunk["metadata"]["total_chunks"] = len(chunks)
        
        # Store chunks if Supabase is available
        stored_chunks = []
        if SUPABASE_AVAILABLE and "supabase" in self.available_backends:
            supabase_backend = self.available_backends["supabase"]
            supabase_api = supabase_backend["api"]
            
            for chunk in chunks:
                try:
                    chunk_result = supabase_api.store_chunk(document_id, chunk)
                    stored_chunks.append({
                        "chunk_id": chunk["chunk_id"],
                        "storage_result": chunk_result
                    })
                except Exception as e:
                    logger.error(f"Error storing chunk in Supabase: {str(e)}")
        
        return {
            "document_id": document_id,
            "total_chunks": len(chunks),
            "chunks": chunks if options.get("return_chunks", False) else [
                {
                    "chunk_id": c["chunk_id"],
                    "start_index": c["start_index"],
                    "end_index": c["end_index"],
                    "length": len(c["text"])
                } for c in chunks
            ],
            "stored_chunks": len(stored_chunks),
            "chunking_options": options,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "status": "success"
        }
    
    # Helper methods
    def _get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Get information about a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary containing file information
        """
        if not os.path.exists(file_path):
            raise ValueError(f"File not found: {file_path}")
        
        # Get file size
        size_bytes = os.path.getsize(file_path)
        
        # Get file modification time
        mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
        
        # Calculate file checksum
        checksum = self._calculate_file_checksum(file_path)
        
        # Determine content type based on extension
        extension = os.path.splitext(file_path)[1].lower()
        content_type = self._get_content_type(extension)
        
        return {
            "filename": os.path.basename(file_path),
            "path": file_path,
            "size_bytes": size_bytes,
            "modified_at": mod_time.isoformat() + "Z",
            "checksum": checksum,
            "content_type": content_type,
            "extension": extension
        }
    
    def _calculate_file_checksum(self, file_path: str) -> str:
        """
        Calculate a checksum for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            SHA-256 checksum as a hex string
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return f"sha256:{hasher.hexdigest()}"
    
    def _get_content_type(self, extension: str) -> str:
        """
        Get the content type for a file extension.
        
        Args:
            extension: File extension
            
        Returns:
            Content type string
        """
        # Common content types
        content_types = {
            ".txt": "text/plain",
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xls": "application/vnd.ms-excel",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".ppt": "application/vnd.ms-powerpoint",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".html": "text/html",
            ".htm": "text/html",
            ".json": "application/json",
            ".xml": "application/xml",
            ".csv": "text/csv",
            ".md": "text/markdown"
        }
        
        return content_types.get(extension, "application/octet-stream")
    
    def _select_storage_backends(self, storage_options: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Select storage backends based on options.
        
        Args:
            storage_options: Dictionary of storage options
            
        Returns:
            Dictionary of selected backends
        """
        # Default is to use all enabled backends
        backends = {}
        for backend_name, backend in self.available_backends.items():
            if backend["enabled"]:
                backends[backend_name] = backend
        
        # Apply specific backend selection if provided
        if "backends" in storage_options:
            specified_backends = storage_options["backends"]
            if specified_backends:
                backends = {}
                for backend_name in specified_backends:
                    if backend_name in self.available_backends and self.available_backends[backend_name]["enabled"]:
                        backends[backend_name] = self.available_backends[backend_name]
        
        # Always include at least the local backend
        if not backends and "local" in self.available_backends:
            backends["local"] = self.available_backends["local"]
        
        return backends
    
    def _store_in_backend(self, backend_name: str, backend: Dict[str, Any], 
                       document_path: str, document_id: str, 
                       metadata: Dict[str, Any]) -> str:
        """
        Store a document in a specific backend.
        
        Args:
            backend_name: Name of the backend
            backend: Backend configuration
            document_path: Path to the document
            document_id: ID of the document
            metadata: Document metadata
            
        Returns:
            Storage path in the backend
        """
        if backend_name == "local":
            # Store in local file system
            return self._store_in_local(document_path, document_id, metadata)
        elif backend_name == "supabase" and backend["api"]:
            # Store in Supabase
            return self._store_in_supabase(backend["api"], document_path, document_id, metadata)
        else:
            raise ValueError(f"Unsupported backend: {backend_name}")
    
    def _store_in_local(self, document_path: str, document_id: str, metadata: Dict[str, Any]) -> str:
        """
        Store a document in the local file system.
        
        Args:
            document_path: Path to the document
            document_id: ID of the document
            metadata: Document metadata
            
        Returns:
            Storage path
        """
        # Create storage directory
        tier = metadata["storage_tier"]
        storage_dir = os.path.join(self.data_dir, "storage", tier, document_id)
        os.makedirs(storage_dir, exist_ok=True)
        
        # Copy the document
        dest_path = os.path.join(storage_dir, os.path.basename(document_path))
        shutil.copy2(document_path, dest_path)
        
        # Write metadata
        meta_path = os.path.join(storage_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        
        return dest_path
    
    def _store_in_supabase(self, supabase_api: Any, document_path: str, 
                       document_id: str, metadata: Dict[str, Any]) -> str:
        """
        Store a document in Supabase.
        
        Args:
            supabase_api: Supabase API client
            document_path: Path to the document
            document_id: ID of the document
            metadata: Document metadata
            
        Returns:
            Storage identifier in Supabase
        """
        # For simplicity, we'll use a placeholder implementation
        # In a real implementation, you would use the Supabase client to store the document
        
        # Read the document content
        with open(document_path, "rb") as f:
            content = f.read()
        
        # Create a storage identifier
        storage_id = f"supabase:{document_id}"
        
        # Log the storage operation
        logger.info(f"Stored document {document_id} in Supabase (placeholder)")
        
        return storage_id
    
    def _select_retrieval_backend(self, storage_locations: Dict[str, str]) -> Tuple[str, str]:
        """
        Select the best backend for retrieval.
        
        Args:
            storage_locations: Dictionary of storage locations by backend
            
        Returns:
            Tuple of (backend_name, location)
        """
        # Try to find a backend in order of priority
        for backend in self.backend_priorities:
            if backend in storage_locations and backend in self.available_backends:
                if self.available_backends[backend]["enabled"]:
                    return backend, storage_locations[backend]
        
        # Fall back to the first available location
        for backend, location in storage_locations.items():
            if backend in self.available_backends:
                if self.available_backends[backend]["enabled"]:
                    return backend, location
        
        raise ValueError("No valid storage backend found for retrieval")
    
    def _retrieve_from_backend(self, backend_name: str, location: str, output_path: str) -> str:
        """
        Retrieve a document from a specific backend.
        
        Args:
            backend_name: Name of the backend
            location: Storage location in the backend
            output_path: Path to save the retrieved document
            
        Returns:
            Path to the retrieved document
        """
        if backend_name == "local":
            # Retrieve from local file system
            if os.path.exists(location):
                # Create output directory
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                shutil.copy2(location, output_path)
                return output_path
            else:
                raise ValueError(f"Document not found at location: {location}")
        elif backend_name == "supabase":
            # Placeholder for retrieving from Supabase
            # In a real implementation, you would use the Supabase client to retrieve the document
            logger.info(f"Retrieved document from Supabase: {location} (placeholder)")
            return output_path
        else:
            raise ValueError(f"Unsupported backend: {backend_name}")
    
    def _delete_from_backend(self, backend_name: str, backend: Dict[str, Any], location: str) -> bool:
        """
        Delete a document from a specific backend.
        
        Args:
            backend_name: Name of the backend
            backend: Backend configuration
            location: Storage location in the backend
            
        Returns:
            True if deletion was successful
        """
        if backend_name == "local":
            # Delete from local file system
            if os.path.exists(location):
                os.remove(location)
                # Delete metadata file if it exists
                metadata_path = os.path.join(os.path.dirname(location), "metadata.json")
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                return True
            return False
        elif backend_name == "supabase" and backend["api"]:
            # Placeholder for deleting from Supabase
            # In a real implementation, you would use the Supabase client to delete the document
            logger.info(f"Deleted document from Supabase: {location} (placeholder)")
            return True
        else:
            return False
    
    def _create_document_index_entry(self, document_id: str, metadata: Dict[str, Any], 
                                  storage_locations: Dict[str, str]) -> None:
        """
        Create an index entry for a document.
        
        Args:
            document_id: ID of the document
            metadata: Document metadata
            storage_locations: Dictionary of storage locations by backend
        """
        index_dir = os.path.join(self.data_dir, "index")
        os.makedirs(index_dir, exist_ok=True)
        
        index_path = os.path.join(index_dir, f"{document_id}.json")
        
        index_entry = {
            "document_id": document_id,
            "metadata": metadata,
            "storage_locations": storage_locations,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
        
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_entry, f, indent=2)
    
    def _get_document_index_entry(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the index entry for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            Document index entry or None if not found
        """
        index_path = os.path.join(self.data_dir, "index", f"{document_id}.json")
        
        if not os.path.exists(index_path):
            return None
        
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading document index entry: {str(e)}")
            return None
    
    def _update_document_index_entry(self, document_id: str, metadata: Dict[str, Any], 
                                  storage_locations: Dict[str, str]) -> None:
        """
        Update the index entry for a document.
        
        Args:
            document_id: ID of the document
            metadata: Document metadata
            storage_locations: Dictionary of storage locations by backend
        """
        index_dir = os.path.join(self.data_dir, "index")
        os.makedirs(index_dir, exist_ok=True)
        
        index_path = os.path.join(index_dir, f"{document_id}.json")
        
        index_entry = {
            "document_id": document_id,
            "metadata": metadata,
            "storage_locations": storage_locations,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
        
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_entry, f, indent=2)
    
    def _delete_document_index_entry(self, document_id: str) -> bool:
        """
        Delete the index entry for a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            True if deletion was successful
        """
        index_path = os.path.join(self.data_dir, "index", f"{document_id}.json")
        
        if os.path.exists(index_path):
            os.remove(index_path)
            return True
        return False
    
    def _archive_document_version(self, document_id: str, document_index: Dict[str, Any]) -> None:
        """
        Archive a document version.
        
        Args:
            document_id: ID of the document
            document_index: Document index entry
        """
        versions_dir = os.path.join(self.data_dir, "versions", document_id)
        os.makedirs(versions_dir, exist_ok=True)
        
        version = document_index["metadata"]["version"]
        version_path = os.path.join(versions_dir, f"{version}.json")
        
        with open(version_path, "w", encoding="utf-8") as f:
            json.dump(document_index, f, indent=2)
    
    def _get_document_versions(self, document_id: str) -> List[str]:
        """
        Get all versions of a document.
        
        Args:
            document_id: ID of the document
            
        Returns:
            List of version strings
        """
        versions_dir = os.path.join(self.data_dir, "versions", document_id)
        
        if not os.path.exists(versions_dir):
            return []
        
        version_files = [f for f in os.listdir(versions_dir) if f.endswith(".json")]
        return [os.path.splitext(f)[0] for f in version_files]
    
    def _get_document_version(self, document_id: str, version: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific version of a document.
        
        Args:
            document_id: ID of the document
            version: Version string
            
        Returns:
            Document version index entry or None if not found
        """
        version_path = os.path.join(self.data_dir, "versions", document_id, f"{version}.json")
        
        if not os.path.exists(version_path):
            return None
        
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading document version: {str(e)}")
            return None
    
    def _update_document_version(self, document_id: str, version: str, metadata: Dict[str, Any], 
                               storage_locations: Dict[str, str]) -> None:
        """
        Update a specific version of a document.
        
        Args:
            document_id: ID of the document
            version: Version string
            metadata: Document metadata
            storage_locations: Dictionary of storage locations by backend
        """
        versions_dir = os.path.join(self.data_dir, "versions", document_id)
        os.makedirs(versions_dir, exist_ok=True)
        
        version_path = os.path.join(versions_dir, f"{version}.json")
        
        version_entry = {
            "document_id": document_id,
            "metadata": metadata,
            "storage_locations": storage_locations,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
        
        with open(version_path, "w", encoding="utf-8") as f:
            json.dump(version_entry, f, indent=2)
    
    def _delete_document_version_entry(self, document_id: str, version: str) -> bool:
        """
        Delete a specific version entry for a document.
        
        Args:
            document_id: ID of the document
            version: Version string
            
        Returns:
            True if deletion was successful
        """
        version_path = os.path.join(self.data_dir, "versions", document_id, f"{version}.json")
        
        if os.path.exists(version_path):
            os.remove(version_path)
            return True
        return False
    
    def _create_backup_index_entry(self, document_id: str, backup_id: str, 
                                backup_metadata: Dict[str, Any]) -> None:
        """
        Create an index entry for a backup.
        
        Args:
            document_id: ID of the document
            backup_id: ID of the backup
            backup_metadata: Backup metadata
        """
        index_dir = os.path.join(self.data_dir, "index")
        os.makedirs(index_dir, exist_ok=True)
        
        index_path = os.path.join(index_dir, f"backup_{document_id}_{backup_id}.json")
        
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(backup_metadata, f, indent=2)
    
    def _get_backup_index_entry(self, document_id: str, backup_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the index entry for a backup.
        
        Args:
            document_id: ID of the document
            backup_id: ID of the backup
            
        Returns:
            Backup index entry or None if not found
        """
        index_path = os.path.join(self.data_dir, "index", f"backup_{document_id}_{backup_id}.json")
        
        if not os.path.exists(index_path):
            return None
        
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading backup index entry: {str(e)}")
            return None
    
    def _update_storage_stats(self, operation: str, result: Dict[str, Any]) -> None:
        """
        Update storage statistics after an operation.
        
        Args:
            operation: Name of the operation
            result: Operation result
        """
        # Update operations count
        if operation in self.storage_stats["operations_count"]:
            self.storage_stats["operations_count"][operation] += 1
        
        # Update other stats based on operation
        if operation == "store":
            # Update document count
            self.storage_stats["total_documents"] += 1
            
            # Update size
            if "storage_metadata" in result and "size_bytes" in result["storage_metadata"]:
                self.storage_stats["total_size_bytes"] += result["storage_metadata"]["size_bytes"]
            
            # Update document type counts
            if "content_type" in result.get("storage_metadata", {}):
                content_type = result["storage_metadata"]["content_type"]
                if content_type in self.storage_stats["documents_by_type"]:
                    self.storage_stats["documents_by_type"][content_type] += 1
                else:
                    self.storage_stats["documents_by_type"][content_type] = 1
        
        # Update timestamp
        self.storage_stats["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def _refresh_storage_stats(self) -> None:
        """Refresh storage statistics by scanning the index directory."""
        # Reset stats
        self.storage_stats["total_documents"] = 0
        self.storage_stats["total_size_bytes"] = 0
        self.storage_stats["documents_by_type"] = {}
        
        # Get document index directory
        index_dir = os.path.join(self.data_dir, "index")
        
        # Check if index directory exists
        if not os.path.exists(index_dir):
            return
        
        # Count documents and sizes
        for index_file in os.listdir(index_dir):
            if index_file.endswith(".json") and not index_file.startswith("backup_"):
                try:
                    with open(os.path.join(index_dir, index_file), "r", encoding="utf-8") as f:
                        document_index = json.load(f)
                    
                    # Skip deleted documents
                    if document_index["metadata"].get("deleted", False):
                        continue
                    
                    # Count document
                    self.storage_stats["total_documents"] += 1
                    
                    # Add size
                    if "size_bytes" in document_index["metadata"]:
                        self.storage_stats["total_size_bytes"] += document_index["metadata"]["size_bytes"]
                    
                    # Count by content type
                    if "content_type" in document_index["metadata"]:
                        content_type = document_index["metadata"]["content_type"]
                        if content_type in self.storage_stats["documents_by_type"]:
                            self.storage_stats["documents_by_type"][content_type] += 1
                        else:
                            self.storage_stats["documents_by_type"][content_type] = 1
                except Exception as e:
                    logger.warning(f"Error loading document index {index_file}: {str(e)}")
        
        # Update timestamp
        self.storage_stats["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def _get_disk_usage(self) -> Dict[str, int]:
        """
        Get disk usage information.
        
        Returns:
            Dictionary with disk usage information
        """
        try:
            # Get disk usage information for the data directory
            usage = shutil.disk_usage(self.data_dir)
            
            return {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "available": usage.free,
                "percent": (usage.used / usage.total) * 100
            }
        except Exception as e:
            logger.error(f"Error getting disk usage: {str(e)}")
            return {
                "total": 0,
                "used": 0,
                "free": 0,
                "available": 0,
                "percent": 0
            }
    
    def _matches_filter_criteria(self, metadata: Dict[str, Any], 
                              filter_criteria: Dict[str, Any]) -> bool:
        """
        Check if metadata matches filter criteria.
        
        Args:
            metadata: Document metadata
            filter_criteria: Dictionary of filter criteria
            
        Returns:
            True if metadata matches all criteria
        """
        for key, value in filter_criteria.items():
            # Handle nested fields with dot notation
            if "." in key:
                parts = key.split(".")
                current = metadata
                for part in parts[:-1]:
                    if part not in current:
                        return False
                    current = current[part]
                
                if parts[-1] not in current or current[parts[-1]] != value:
                    return False
            else:
                # Handle direct fields
                if key not in metadata or metadata[key] != value:
                    return False
        
        return True
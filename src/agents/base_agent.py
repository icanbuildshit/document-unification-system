from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import os
import json
import uuid
import time
from datetime import datetime
import hashlib
from dotenv import load_dotenv

from loguru import logger

# Load environment variables
load_dotenv()

class BaseAgent(ABC):
    """Base class for all agents in the document unification system"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.agent_id = str(uuid.uuid4())
        # Load configuration from environment if not provided
        self.log_level = self.config.get("log_level", os.getenv("LOG_LEVEL", "INFO"))
        logger.info(f"Initializing {self.name} agent with ID {self.agent_id}")
        
    @abstractmethod
    async def process(self, input_data: Any) -> Any:
        """Main processing method to be implemented by each agent"""
        pass
    
    def _save_intermediate_output(self, data: Any, stage: str, format: str = "json") -> str:
        """Save intermediate output for versioning and audit trail"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join("output", "intermediate", self.name)
        os.makedirs(output_dir, exist_ok=True)
        
        # Create a version identifier
        content_hash = hashlib.md5(str(data).encode()).hexdigest()[:8]
        filename = f"{stage}_{timestamp}_{content_hash}.{format}"
        filepath = os.path.join(output_dir, filename)
        
        # Save the data based on format
        if format == "json":
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(str(data))
        
        logger.debug(f"Saved intermediate output to {filepath}")
        return filepath
    
    def _create_audit_entry(self, action: str, input_ref: str, output_ref: str, 
                           metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create an audit trail entry"""
        audit_entry = {
            "agent": self.name,
            "agent_id": self.agent_id,
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "input_reference": input_ref,
            "output_reference": output_ref,
            "metadata": metadata or {}
        }
        
        # Append to audit log
        audit_dir = os.path.join("output", "audit")
        os.makedirs(audit_dir, exist_ok=True)
        audit_file = os.path.join(audit_dir, "audit_trail.jsonl")
        
        with open(audit_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(audit_entry) + "\n")
        
        return audit_entry

class AuditLogger:
    def __init__(self, name="orchestrator", agent_id="orchestrator-audit"):
        self.name = name
        self.agent_id = agent_id

    def _create_audit_entry(self, action, input_ref, output_ref, metadata=None):
        audit_entry = {
            "agent": self.name,
            "agent_id": self.agent_id,
            "action": action,
            "timestamp": datetime.now().isoformat(),
            "input_reference": input_ref,
            "output_reference": output_ref,
            "metadata": metadata or {}
        }
        audit_dir = os.path.join("output", "audit")
        os.makedirs(audit_dir, exist_ok=True)
        audit_file = os.path.join(audit_dir, "audit_trail.jsonl")
        with open(audit_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(audit_entry) + "\n")
        return audit_entry 
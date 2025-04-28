"""
Tiered memory management system for agents.
Implements short-term, working, and long-term memory.
"""

from typing import Dict, List, Any, Optional
import time
import json
import os
import pickle
from datetime import datetime
import hashlib
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import redis

class TieredMemory:
    """
    Implements a three-tiered memory system:
    - Short-term: Volatile, fast access, limited capacity
    - Working: Semi-persistent, moderate capacity
    - Long-term: Persistent, large capacity, slower access
    """
    def __init__(self, agent_name: str, config: Dict[str, Any] = None):
        self.agent_name = agent_name
        self.config = config or {}
        # Short-term memory (in-memory dict)
        self.short_term_memory = {}
        self.stm_max_items = self.config.get("stm_max_items", 100)
        self.stm_ttl = self.config.get("stm_ttl", 600)  # 10 minutes
        # Working memory (Redis if available, fallback to file)
        self.redis_available = False
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            self.redis = redis.Redis(host=redis_host, port=redis_port)
            self.redis.ping()
            self.redis_available = True
        except:
            self.working_memory_file = f"data/intermediate/{agent_name}_working_memory.json"
            os.makedirs(os.path.dirname(self.working_memory_file), exist_ok=True)
            if not os.path.exists(self.working_memory_file):
                with open(self.working_memory_file, 'w') as f:
                    json.dump({}, f)
        # Long-term memory (vector embeddings + metadata store)
        self.ltm_dir = f"data/intermediate/{agent_name}_long_term_memory"
        os.makedirs(self.ltm_dir, exist_ok=True)
        self.vector_file = os.path.join(self.ltm_dir, "vectors.pkl")
        self.metadata_file = os.path.join(self.ltm_dir, "metadata.json")
        self.vectors = []
        self.vector_keys = []
        self.metadata = {}
        self._load_long_term_memory()
        model_name = self.config.get("embedding_model", "all-MiniLM-L6-v2")
        self.embedding_model = SentenceTransformer(model_name)
    # Short-term memory methods
    def store_stm(self, key: str, value: Any) -> None:
        self.short_term_memory[key] = {"value": value, "timestamp": time.time()}
        if len(self.short_term_memory) > self.stm_max_items:
            oldest_key = min(self.short_term_memory.keys(), key=lambda k: self.short_term_memory[k]["timestamp"])
            del self.short_term_memory[oldest_key]
    def retrieve_stm(self, key: str) -> Optional[Any]:
        if key in self.short_term_memory:
            item = self.short_term_memory[key]
            if time.time() - item["timestamp"] > self.stm_ttl:
                del self.short_term_memory[key]
                return None
            return item["value"]
        return None
    # Working memory methods
    def store_wm(self, key: str, value: Any, ttl: int = 86400) -> None:
        if self.redis_available:
            self.redis.setex(f"{self.agent_name}:{key}", ttl, json.dumps(value))
        else:
            with open(self.working_memory_file, 'r') as f:
                working_memory = json.load(f)
            working_memory[key] = {"value": value, "expires_at": time.time() + ttl}
            with open(self.working_memory_file, 'w') as f:
                json.dump(working_memory, f)
    def retrieve_wm(self, key: str) -> Optional[Any]:
        if self.redis_available:
            value = self.redis.get(f"{self.agent_name}:{key}")
            if value:
                return json.loads(value)
            return None
        else:
            with open(self.working_memory_file, 'r') as f:
                working_memory = json.load(f)
            if key in working_memory:
                item = working_memory[key]
                if time.time() > item["expires_at"]:
                    del working_memory[key]
                    with open(self.working_memory_file, 'w') as f:
                        json.dump(working_memory, f)
                    return None
                return item["value"]
            return None
    # Long-term memory methods
    def store_ltm(self, text: str, metadata: Dict[str, Any] = None) -> str:
        embedding = self.embedding_model.encode(text)
        memory_id = hashlib.md5(text.encode()).hexdigest()[:16]
        self.vectors.append(embedding)
        self.vector_keys.append(memory_id)
        self.metadata[memory_id] = {
            "text": text,
            "metadata": metadata or {},
            "created_at": datetime.now().isoformat()
        }
        self._save_long_term_memory()
        return memory_id
    def search_ltm(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        if not self.vectors:
            return []
        query_embedding = self.embedding_model.encode(query)
        similarities = cosine_similarity([query_embedding], self.vectors)[0]
        top_indices = np.argsort(similarities)[-top_k:][::-1]
        results = []
        for idx in top_indices:
            memory_id = self.vector_keys[idx]
            results.append({
                "id": memory_id,
                "text": self.metadata[memory_id]["text"],
                "metadata": self.metadata[memory_id]["metadata"],
                "similarity": float(similarities[idx]),
                "created_at": self.metadata[memory_id]["created_at"]
            })
        return results
    def _load_long_term_memory(self) -> None:
        try:
            if os.path.exists(self.vector_file):
                with open(self.vector_file, 'rb') as f:
                    vectors_data = pickle.load(f)
                    self.vectors = vectors_data["vectors"]
                    self.vector_keys = vectors_data["keys"]
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
        except Exception as e:
            print(f"Error loading long-term memory: {str(e)}")
            self.vectors = []
            self.vector_keys = []
            self.metadata = {}
    def _save_long_term_memory(self) -> None:
        try:
            with open(self.vector_file, 'wb') as f:
                pickle.dump({"vectors": self.vectors, "keys": self.vector_keys}, f)
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f)
        except Exception as e:
            print(f"Error saving long-term memory: {str(e)}") 
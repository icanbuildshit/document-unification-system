"""
Supabase/PostgreSQL storage module for document chunks and keywords.
"""

from supabase import create_client, Client
import os

class SupabaseStorage:
    """
    Supabase/PostgreSQL storage for document chunks and keywords.
    TODO:
    - Implement real upsert/insert logic for production.
    - Add error handling, retries, and logging.
    - Support batch operations and schema migrations.
    """
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        self.client: Client = create_client(url, key)
        self.chunks_table = "document_chunks"
        self.keywords_table = "chunk_keywords"

    def store_chunk(self, document_id, chunk):
        """
        Store a document chunk in Supabase/PostgreSQL.
        Args:
            document_id (str): The document's unique ID.
            chunk (dict): Chunk data to store.
        Returns:
            dict: Inserted record or response.
        """
        from datetime import datetime
        import json
        try:
            data = {
                "document_id": document_id,
                "text": chunk.get("text"),
                "metadata": json.dumps(chunk.get("metadata", {})),
                "created_at": datetime.utcnow().isoformat()
            }
            response = self.client.table(self.chunks_table).insert(data).execute()
            self._log_action(
                action="store_chunk",
                target=self.chunks_table,
                result="success" if response.data else "error",
                rationale=f"Stored chunk for document {document_id}.",
                extra={"response": str(response.data)}
            )
            return response.data
        except Exception as e:
            self._log_action(
                action="store_chunk",
                target=self.chunks_table,
                result="error",
                rationale=f"Failed to store chunk for document {document_id}: {e}",
                extra={}
            )
            return None

    def store_keywords(self, chunk_id, keywords):
        """
        Store keywords associated with a chunk.
        Args:
            chunk_id (str): The chunk's unique ID.
            keywords (list): List of keywords.
        Returns:
            dict: Inserted record or response.
        """
        from datetime import datetime
        import json
        try:
            data = {
                "chunk_id": chunk_id,
                "keywords": json.dumps(keywords),
                "created_at": datetime.utcnow().isoformat()
            }
            response = self.client.table(self.keywords_table).insert(data).execute()
            self._log_action(
                action="store_keywords",
                target=self.keywords_table,
                result="success" if response.data else "error",
                rationale=f"Stored keywords for chunk {chunk_id}.",
                extra={"response": str(response.data)}
            )
            return response.data
        except Exception as e:
            self._log_action(
                action="store_keywords",
                target=self.keywords_table,
                result="error",
                rationale=f"Failed to store keywords for chunk {chunk_id}: {e}",
                extra={}
            )
            return None

    def _log_action(self, action, target, result, rationale, extra):
        from datetime import datetime
        log_entry = (
            f"[{datetime.utcnow().isoformat()}Z] ACTION: \"{action}\"\n"
            f"TARGET: \"{target}\"\n"
            f"RESULT: \"{result}\"\n"
            f"RATIONALE: \"{rationale}\"\n"
            f"EXTRA: {extra}\n"
        )
        log_path = "output/audit/audit_trail.jsonl"
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")

class StorageAgent:
    """
    Specialized agent for storage, for use in multi-agent orchestration.
    TODO:
    - Add support for distributed storage and sharding.
    - Integrate with monitoring/logging.
    - Add hooks for custom storage post-processing.
    """
    def __init__(self):
        self.storage = SupabaseStorage()

    def store_chunk(self, document_id, chunk):
        """
        Store a document chunk.
        """
        return self.storage.store_chunk(document_id, chunk)

    def store_keywords(self, chunk_id, keywords):
        """
        Store keywords for a chunk.
        """
        return self.storage.store_keywords(chunk_id, keywords) 
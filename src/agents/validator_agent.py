from typing import Dict, List, Any, Tuple
import spacy
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from src.agents.base_agent import BaseAgent
from loguru import logger

class ValidatorAgent(BaseAgent):
    """
    Agent responsible for cross-referencing facts across documents,
    flagging contradictions, and maintaining a provenance trail.
    """
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("validator", config)
        self.nlp = spacy.load("en_core_web_sm")
        self.sentence_model = SentenceTransformer('all-MiniLM-L6-v2')
        self.similarity_threshold = self.config.get("similarity_threshold", 0.8)
        self.contradiction_threshold = self.config.get("contradiction_threshold", 0.6)
    async def process(self, parser_output: Dict[str, Any]) -> Dict[str, Any]:
        documents = parser_output.get("documents", [])
        successful_docs = [doc for doc in documents if doc.get("status") == "success"]
        all_chunks = self._extract_all_chunks(successful_docs)
        facts, facts_to_chunks = self._extract_facts(all_chunks)
        contradiction_results = self._find_contradictions(facts, facts_to_chunks)
        validated_documents = self._add_validation_to_documents(
            documents, contradiction_results, facts
        )
        result = {
            "documents": validated_documents,
            "validation_results": {
                "status": "success",
                "stats": {
                    "total_facts": len(facts),
                    "total_contradictions": len(contradiction_results),
                    "documents_validated": len(successful_docs)
                },
                "contradictions": contradiction_results
            }
        }
        return result
    def _extract_all_chunks(self, documents):
        chunks = []
        for doc in documents:
            for chunk in doc.get("content", {}).get("chunks", []):
                chunks.append(chunk)
        return chunks
    def _extract_facts(self, chunks):
        facts = []
        facts_to_chunks = {}
        for idx, chunk in enumerate(chunks):
            doc = self.nlp(chunk["text"])
            for ent in doc.ents:
                fact = {
                    "text": ent.text,
                    "label": ent.label_,
                    "chunk_idx": idx
                }
                facts.append(fact)
                facts_to_chunks.setdefault(ent.text, []).append(idx)
        return facts, facts_to_chunks
    def _find_contradictions(self, facts, facts_to_chunks):
        contradictions = []
        # Simple contradiction detection: same label, different values, high similarity
        for i, fact1 in enumerate(facts):
            for j, fact2 in enumerate(facts):
                if i >= j:
                    continue
                if fact1["label"] == fact2["label"] and fact1["text"] != fact2["text"]:
                    sim = self._fact_similarity(fact1["text"], fact2["text"])
                    if sim > self.similarity_threshold:
                        contradictions.append({
                            "fact_type": fact1["label"],
                            "fact_values": [fact1["text"], fact2["text"]],
                            "similarity": sim,
                            "sources": [fact1["chunk_idx"], fact2["chunk_idx"]],
                            "contradiction_id": f"contradiction_{i}_{j}"
                        })
        return contradictions
    def _fact_similarity(self, text1: str, text2: str) -> float:
        emb1 = self.sentence_model.encode([text1])[0]
        emb2 = self.sentence_model.encode([text2])[0]
        return float(cosine_similarity([emb1], [emb2])[0][0])
    def _add_validation_to_documents(self, documents, contradictions, facts):
        for doc in documents:
            doc["validation"] = {
                "contradictions": [c for c in contradictions if doc.get("file_name") in str(c["sources"])],
                "facts": [f for f in facts if doc.get("file_name") in str(f.get("chunk_idx"))]
            }
        return documents 
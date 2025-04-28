"""
Advanced document chunking utilities supporting semantic,
hierarchical, and hybrid chunking approaches.
"""

from typing import Dict, List, Any, Tuple, Optional
import re
import numpy as np
from sklearn.cluster import SpectralClustering
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class AdvancedChunker:
    """
    Implements multiple advanced chunking strategies for document processing.
    """
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        model_name = self.config.get("embedding_model", "all-MiniLM-L6-v2")
        self.embedding_model = SentenceTransformer(model_name)
        self.chunk_min_size = self.config.get("chunk_min_size", 50)
        self.chunk_max_size = self.config.get("chunk_max_size", 1500)
        self.chunk_overlap = self.config.get("chunk_overlap", 100)
        self.semantic_similarity_threshold = self.config.get("semantic_similarity_threshold", 0.75)
        self.spatial_weight = self.config.get("spatial_weight", 0.5)
        self.semantic_weight = self.config.get("semantic_weight", 0.5)
    def semantic_chunking(self, text: str) -> List[str]:
        sentences = self._split_into_sentences(text)
        if not sentences:
            return []
        embeddings = self.embedding_model.encode(sentences)
        similarities = cosine_similarity(embeddings)
        chunks = []
        current_chunk = [sentences[0]]
        current_length = len(sentences[0])
        for i in range(1, len(sentences)):
            similarity = similarities[i, i-1]
            if (similarity < self.semantic_similarity_threshold or 
                current_length + len(sentences[i]) > self.chunk_max_size):
                if current_length < self.chunk_min_size:
                    current_chunk.append(sentences[i])
                    current_length += len(sentences[i])
                else:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = [sentences[i]]
                    current_length = len(sentences[i])
            else:
                current_chunk.append(sentences[i])
                current_length += len(sentences[i])
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        return chunks
    def hierarchical_chunking(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        hierarchy = {}
        for element in elements:
            parent_id = element.get("metadata", {}).get("parent_id", "root")
            if parent_id not in hierarchy:
                hierarchy[parent_id] = []
            hierarchy[parent_id].append(element)
        chunks = []
        self._process_hierarchy(hierarchy, "root", chunks)
        return chunks
    def _process_hierarchy(self, hierarchy: Dict[str, List[Dict]], current_id: str, 
                          chunks: List[Dict], current_chunk: Optional[Dict] = None) -> None:
        if current_id not in hierarchy:
            return
        elements = hierarchy[current_id]
        elements.sort(key=lambda e: (
            e.get("metadata", {}).get("page_number", 0),
            e.get("metadata", {}).get("coordinates", [0, 0])[1]
        ))
        for element in elements:
            element_id = element.get("metadata", {}).get("element_id", "")
            element_type = element.get("metadata", {}).get("type", "")
            if (element_type in ["Title", "Heading", "H1", "H2", "H3"] or 
                (current_chunk and 
                 len(current_chunk["text"]) + len(element["text"]) > self.chunk_max_size)):
                if current_chunk and len(current_chunk["text"]) >= self.chunk_min_size:
                    chunks.append(current_chunk)
                current_chunk = {
                    "text": element["text"],
                    "metadata": {
                        "elements": [element],
                        "types": [element_type],
                        "hierarchy_level": len(element.get("metadata", {}).get("parent_id", "").split("/")),
                        "start_element_id": element_id
                    }
                }
            else:
                if not current_chunk:
                    current_chunk = {
                        "text": element["text"],
                        "metadata": {
                            "elements": [element],
                            "types": [element_type],
                            "hierarchy_level": len(element.get("metadata", {}).get("parent_id", "").split("/")),
                            "start_element_id": element_id
                        }
                    }
                else:
                    current_chunk["text"] += "\n" + element["text"]
                    current_chunk["metadata"]["elements"].append(element)
                    current_chunk["metadata"]["types"].append(element_type)
            self._process_hierarchy(hierarchy, element_id, chunks, current_chunk)
        if current_chunk and (not chunks or chunks[-1] != current_chunk):
            chunks.append(current_chunk)
    def hybrid_spatial_semantic_chunking(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not elements:
            return []
        texts = [element["text"] for element in elements]
        embeddings = self.embedding_model.encode(texts)
        n_elements = len(elements)
        adjacency_matrix = np.zeros((n_elements, n_elements))
        for i in range(n_elements):
            for j in range(i+1, n_elements):
                semantic_sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                spatial_sim = self._calculate_spatial_similarity(elements[i], elements[j])
                combined_sim = (self.semantic_weight * semantic_sim + 
                               self.spatial_weight * spatial_sim)
                adjacency_matrix[i, j] = combined_sim
                adjacency_matrix[j, i] = combined_sim
        n_clusters = max(2, min(int(n_elements / 10), 20))
        clustering = SpectralClustering(
            n_clusters=n_clusters,
            affinity='precomputed',
            assign_labels='kmeans',
            random_state=42
        ).fit(adjacency_matrix)
        clusters = {}
        for i, label in enumerate(clustering.labels_):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(elements[i])
        chunks = []
        for label, cluster_elements in clusters.items():
            cluster_elements.sort(key=lambda e: (
                e.get("metadata", {}).get("page_number", 0),
                e.get("metadata", {}).get("coordinates", [0, 0])[1]
            ))
            chunk_text = "\n".join(element["text"] for element in cluster_elements)
            chunk = {
                "text": chunk_text,
                "metadata": {
                    "elements": cluster_elements,
                    "types": [e.get("metadata", {}).get("type", "") for e in cluster_elements],
                    "cluster_id": label,
                    "page_range": self._get_page_range(cluster_elements)
                }
            }
            chunks.append(chunk)
        return chunks
    def _calculate_spatial_similarity(self, element1: Dict[str, Any], element2: Dict[str, Any]) -> float:
        page1 = element1.get("metadata", {}).get("page_number", -1)
        page2 = element2.get("metadata", {}).get("page_number", -1)
        if page1 != page2 or page1 == -1:
            return 0.0
        coords1 = element1.get("metadata", {}).get("coordinates", None)
        coords2 = element2.get("metadata", {}).get("coordinates", None)
        if not coords1 or not coords2:
            return 0.0
        centroid1 = [(coords1[0] + coords1[2]) / 2, (coords1[1] + coords1[3]) / 2]
        centroid2 = [(coords2[0] + coords2[2]) / 2, (coords2[1] + coords2[3]) / 2]
        distance = np.sqrt((centroid1[0] - centroid2[0])**2 + (centroid1[1] - centroid2[1])**2)
        max_distance = 842
        similarity = max(0, 1 - (distance / max_distance))
        return similarity
    def _get_page_range(self, elements: List[Dict[str, Any]]) -> Tuple[int, int]:
        pages = [e.get("metadata", {}).get("page_number", 0) for e in elements]
        pages = [p for p in pages if p > 0]
        if not pages:
            return (0, 0)
        return (min(pages), max(pages))
    def _split_into_sentences(self, text: str) -> List[str]:
        text = re.sub(r'(?<![A-Z][a-z]\.) (?<=\.|\?|\!)\s+', '\n', text)
        sentences = [s.strip() for s in text.split('\n') if s.strip()]
        return sentences 
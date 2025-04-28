"""
Hybrid spatial-semantic chunking module.
"""

from sentence_transformers import SentenceTransformer
import numpy as np
import networkx as nx
from sklearn.cluster import SpectralClustering

class HybridChunker:
    """
    Hybrid spatial-semantic chunker.
    TODO:
    - Add batch processing and memory optimization for large documents.
    - Add logging and error handling for production.
    - Allow dynamic tuning of alpha and threshold via config.
    """
    def __init__(self, embedding_model_name='all-MiniLM-L6-v2', alpha=0.6, similarity_threshold=0.3):
        """
        alpha: weight for semantic similarity (0-1)
        similarity_threshold: minimum combined weight to create an edge
        """
        self.model = SentenceTransformer(embedding_model_name)
        self.alpha = alpha
        self.similarity_threshold = similarity_threshold

    def chunk(self, elements):
        """
        Chunk document elements using hybrid spatial-semantic approach.
        Args:
            elements (list): List of structured document elements, each with 'text_content' and 'coordinates'.
        Returns:
            list: List of chunks (each chunk is a list of elements).
        """
        if not elements:
            return []

        # Step 1: Compute embeddings for all elements
        texts = [el['text_content'] for el in elements]
        embeddings = self.model.encode(texts)

        # Step 2: Build graph with combined weights
        G = nx.Graph()
        for i, el in enumerate(elements):
            G.add_node(i, data=el)

        for i in range(len(elements)):
            for j in range(i+1, len(elements)):
                # Semantic similarity (cosine)
                emb_i, emb_j = embeddings[i], embeddings[j]
                semantic_sim = np.dot(emb_i, emb_j) / (np.linalg.norm(emb_i) * np.linalg.norm(emb_j) + 1e-8)
                # Spatial proximity (normalized inverse distance)
                spatial_sim = self.calculate_spatial_proximity(elements[i], elements[j])
                # Combined weight
                combined = self.alpha * semantic_sim + (1 - self.alpha) * spatial_sim
                if combined > self.similarity_threshold:
                    G.add_edge(i, j, weight=combined)

        # Step 3: Spectral clustering
        affinity = nx.to_numpy_array(G)
        n_clusters = max(2, min(len(elements) // 10, len(elements)))  # Heuristic: at least 2 clusters
        clustering = SpectralClustering(n_clusters=n_clusters, affinity='precomputed', assign_labels='discretize', random_state=42)
        labels = clustering.fit_predict(affinity)

        # Step 4: Group elements by cluster label
        chunks = {}
        for idx, label in enumerate(labels):
            if label not in chunks:
                chunks[label] = []
            chunks[label].append(elements[idx])
        return list(chunks.values())

    def calculate_spatial_proximity(self, elem1, elem2):
        """
        Calculate spatial proximity between two elements.
        Returns a value in [0,1], where 1 is very close, 0 is far apart.
        Assumes 'coordinates' is a dict with 'x', 'y' or a bounding box.
        """
        c1, c2 = elem1.get('coordinates'), elem2.get('coordinates')
        if not c1 or not c2:
            return 0.0  # No spatial info
        # Use centroid if bounding box, else x/y
        def get_centroid(coord):
            if isinstance(coord, dict):
                if all(k in coord for k in ('x', 'y')):
                    return np.array([coord['x'], coord['y']])
                elif all(k in coord for k in ('x0', 'y0', 'x1', 'y1')):
                    return np.array([(coord['x0'] + coord['x1'])/2, (coord['y0'] + coord['y1'])/2])
            elif isinstance(coord, (list, tuple)) and len(coord) == 2:
                return np.array(coord)
            return np.array([0,0])
        p1, p2 = get_centroid(c1), get_centroid(c2)
        dist = np.linalg.norm(p1 - p2)
        # Normalize distance (assume max doc distance ~1000 for scaling)
        norm_dist = min(dist / 1000.0, 1.0)
        return 1.0 - norm_dist  # Closer = higher similarity 

class ChunkingAgent:
    """
    Specialized agent for chunking, for use in multi-agent orchestration.
    TODO:
    - Add support for distributed chunking.
    - Integrate with monitoring/logging.
    - Add hooks for custom chunk post-processing.
    """
    def __init__(self, **kwargs):
        self.chunker = HybridChunker(**kwargs)

    def process(self, elements):
        """
        Chunk parsed elements.
        Args:
            elements (list): List of parsed document elements.
        Returns:
            list: List of chunks.
        """
        return self.chunker.chunk(elements) 
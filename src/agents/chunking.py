"""
Enhanced hybrid spatial-semantic chunking module with integration to LangChain.

This module provides a sophisticated document chunking system that combines:
1. Spatial proximity - How physically close elements are in a document
2. Semantic similarity - How conceptually related elements are
3. Visual formatting - How elements relate based on styling/formatting

It integrates with LangChain for compatibility with its document processing pipeline
while providing specialized capabilities for complex document layouts.
"""

import logging
from typing import List, Dict, Any, Tuple, Optional, Union, Callable
import time
import uuid

import numpy as np
import networkx as nx
from sklearn.cluster import SpectralClustering, AgglomerativeClustering
from sentence_transformers import SentenceTransformer
import torch
from langchain.schema.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

from src.utils.orchestrator_logging import setup_logger

# Set up logger
logger = setup_logger("chunking")


class ChunkingConfig(BaseModel):
    """Configuration for the chunking process."""
    
    # Model settings
    embedding_model_name: str = "all-MiniLM-L6-v2"
    use_gpu: bool = torch.cuda.is_available()
    batch_size: int = 32
    
    # Chunking parameters
    alpha: float = Field(default=0.6, ge=0.0, le=1.0, 
                         description="Weight for semantic similarity (0-1)")
    spatial_weight: float = Field(default=0.3, ge=0.0, le=1.0, 
                                 description="Weight for spatial proximity")
    formatting_weight: float = Field(default=0.1, ge=0.0, le=1.0, 
                                    description="Weight for visual formatting similarity")
    similarity_threshold: float = Field(default=0.3, ge=0.0, le=1.0, 
                                       description="Minimum combined weight to create an edge")
    
    # Clustering parameters
    clustering_method: str = "spectral"  # "spectral" or "agglomerative"
    min_cluster_size: int = 2
    max_cluster_size: int = 20
    
    # Text-specific settings
    max_chunk_size: int = 2000
    chunk_overlap: int = 200
    
    # Output settings
    include_embeddings: bool = True
    min_content_length: int = 10
    
    class Config:
        """Pydantic config"""
        validate_assignment = True


class DocumentElement(BaseModel):
    """A structured document element with content and metadata."""
    
    # Core content
    text_content: str
    element_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Spatial information
    coordinates: Optional[Dict[str, float]] = None
    page_number: Optional[int] = None
    
    # Visual/formatting information
    font_info: Optional[Dict[str, Any]] = None
    is_header: bool = False
    is_footer: bool = False
    is_table: bool = False
    indentation_level: Optional[int] = None
    
    # Element type info
    element_type: str = "text"  # text, table, image, list, etc.
    
    # Relationships
    parent_id: Optional[str] = None
    child_ids: List[str] = Field(default_factory=list)
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        """Pydantic config"""
        arbitrary_types_allowed = True


class DocumentChunk(BaseModel):
    """A chunk of document elements that are semantically and/or spatially related."""
    
    # Core data
    chunk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    elements: List[DocumentElement]
    
    # Chunk metadata
    page_range: Tuple[int, int] = (0, 0)
    word_count: int = 0
    character_count: int = 0
    
    # Semantic information
    embedding: Optional[List[float]] = None
    embedding_model: Optional[str] = None
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def __init__(self, **data):
        super().__init__(**data)
        # Calculate derived fields if not already provided
        if not self.word_count and self.elements:
            self.word_count = sum(len(elem.text_content.split()) for elem in self.elements)
        if not self.character_count and self.elements:
            self.character_count = sum(len(elem.text_content) for elem in self.elements)
        if not self.page_range and self.elements:
            pages = [elem.page_number for elem in self.elements if elem.page_number is not None]
            if pages:
                self.page_range = (min(pages), max(pages))
    
    def get_combined_text(self) -> str:
        """Get the combined text of all elements in the chunk."""
        return "\n\n".join(elem.text_content for elem in self.elements if elem.text_content)
    
    def to_langchain_document(self) -> Document:
        """Convert to LangChain Document format for compatibility."""
        return Document(
            page_content=self.get_combined_text(),
            metadata={
                "chunk_id": self.chunk_id,
                "page_range": self.page_range,
                "word_count": self.word_count,
                "element_count": len(self.elements),
                **self.metadata
            }
        )
    
    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True


class HybridChunker:
    """
    Enhanced hybrid spatial-semantic chunker with improved clustering and preprocessing.
    Combines multiple signals (semantic, spatial, visual) for more intelligent document chunking.
    """
    
    def __init__(self, config: Optional[Union[ChunkingConfig, Dict[str, Any]]] = None):
        """
        Initialize the chunker with configuration.
        
        Args:
            config: ChunkingConfig object or dict with configuration parameters
        """
        if config is None:
            self.config = ChunkingConfig()
        elif isinstance(config, dict):
            self.config = ChunkingConfig(**config)
        else:
            self.config = config
        
        # Initialize embedding model
        logger.info(f"Initializing embedding model: {self.config.embedding_model_name}")
        self.model = SentenceTransformer(self.config.embedding_model_name)
        
        # Use GPU if available and requested
        if self.config.use_gpu and torch.cuda.is_available():
            self.model = self.model.to(torch.device("cuda"))
            logger.info("Using GPU for embeddings")
        
        # Text splitter for long texts
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.max_chunk_size,
            chunk_overlap=self.config.chunk_overlap
        )
        
        logger.info("HybridChunker initialized successfully")
    
    def chunk(self, elements: List[Union[DocumentElement, Dict[str, Any]]]) -> List[DocumentChunk]:
        """
        Chunk document elements using hybrid spatial-semantic approach.
        
        Args:
            elements: List of DocumentElement objects or dicts with at least 'text_content' key
            
        Returns:
            List of DocumentChunk objects
        """
        start_time = time.time()
        logger.info(f"Starting chunking process for {len(elements)} elements")
        
        if not elements:
            logger.warning("No elements provided for chunking")
            return []
        
        # Convert dict elements to DocumentElement if needed
        processed_elements = []
        for el in elements:
            if isinstance(el, dict):
                # Filter out very short content
                if len(el.get('text_content', '').strip()) < self.config.min_content_length:
                    continue
                processed_elements.append(DocumentElement(**el))
            else:
                # Filter out very short content
                if len(el.text_content.strip()) < self.config.min_content_length:
                    continue
                processed_elements.append(el)
        
        if not processed_elements:
            logger.warning("No valid elements after preprocessing")
            return []
        
        # Step 1: Compute embeddings for all elements
        texts = [el.text_content for el in processed_elements]
        
        # Batch process embeddings for memory efficiency
        logger.debug(f"Computing embeddings for {len(texts)} texts")
        embeddings = []
        batch_size = self.config.batch_size
        
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_embeddings = self.model.encode(
                batch_texts, 
                show_progress_bar=False, 
                convert_to_numpy=True
            )
            embeddings.extend(batch_embeddings)
        
        embeddings = np.array(embeddings)
        
        # Step 2: Build graph with combined weights
        logger.debug("Building similarity graph")
        G = nx.Graph()
        for i, el in enumerate(processed_elements):
            G.add_node(i, data=el)
        
        for i in range(len(processed_elements)):
            for j in range(i+1, len(processed_elements)):
                # 1. Semantic similarity (cosine)
                emb_i, emb_j = embeddings[i], embeddings[j]
                semantic_sim = np.dot(emb_i, emb_j) / (np.linalg.norm(emb_i) * np.linalg.norm(emb_j) + 1e-8)
                
                # 2. Spatial proximity
                spatial_sim = self._calculate_spatial_proximity(processed_elements[i], processed_elements[j])
                
                # 3. Formatting similarity
                formatting_sim = self._calculate_formatting_similarity(processed_elements[i], processed_elements[j])
                
                # Combined weight with configurable parameters
                combined = (
                    self.config.alpha * semantic_sim + 
                    self.config.spatial_weight * spatial_sim + 
                    self.config.formatting_weight * formatting_sim
                )
                
                if combined > self.config.similarity_threshold:
                    G.add_edge(i, j, weight=combined)
        
        # Step 3: Apply clustering algorithm
        logger.debug(f"Clustering using {self.config.clustering_method} method")
        
        if self.config.clustering_method == "spectral":
            cluster_labels = self._apply_spectral_clustering(G, processed_elements)
        elif self.config.clustering_method == "agglomerative":
            cluster_labels = self._apply_agglomerative_clustering(G, processed_elements)
        else:
            # Fallback to connected components if method not recognized
            logger.warning(f"Unknown clustering method: {self.config.clustering_method}, using connected components")
            cluster_labels = self._get_connected_components(G)
        
        # Step 4: Group elements by cluster label and create chunks
        logger.debug("Creating chunk objects from clusters")
        chunks = {}
        for idx, label in enumerate(cluster_labels):
            if label not in chunks:
                chunks[label] = []
            chunks[label].append(processed_elements[idx])
        
        # Create DocumentChunk objects
        document_chunks = []
        for label, elements_list in chunks.items():
            # Calculate average embedding for the chunk if requested
            chunk_embedding = None
            if self.config.include_embeddings:
                indices = [processed_elements.index(el) for el in elements_list]
                chunk_embedding = np.mean(embeddings[indices], axis=0).tolist()
            
            # Create the chunk
            chunk = DocumentChunk(
                elements=elements_list,
                embedding=chunk_embedding,
                embedding_model=self.config.embedding_model_name if chunk_embedding else None,
                metadata={"cluster_label": int(label)}
            )
            document_chunks.append(chunk)
        
        # Log performance metrics
        elapsed_time = time.time() - start_time
        logger.info(f"Chunking completed: {len(document_chunks)} chunks created in {elapsed_time:.2f} seconds")
        
        return document_chunks
    
    def _calculate_spatial_proximity(self, elem1: DocumentElement, elem2: DocumentElement) -> float:
        """
        Calculate spatial proximity between two elements.
        Returns a value in [0,1], where 1 is very close, 0 is far apart.
        """
        # Same page gets a proximity boost
        if elem1.page_number is not None and elem2.page_number is not None:
            if elem1.page_number != elem2.page_number:
                return 0.1  # Different pages have low proximity
        
        c1, c2 = elem1.coordinates, elem2.coordinates
        if not c1 or not c2:
            return 0.2  # Default proximity when spatial info is missing
        
        # Calculate centroid points
        def get_centroid(coord: Dict[str, float]) -> np.ndarray:
            if all(k in coord for k in ('x', 'y')):
                return np.array([coord['x'], coord['y']])
            elif all(k in coord for k in ('x0', 'y0', 'x1', 'y1')):
                return np.array([(coord['x0'] + coord['x1'])/2, (coord['y0'] + coord['y1'])/2])
            return np.array([0, 0])
        
        p1, p2 = get_centroid(c1), get_centroid(c2)
        
        # Calculate Euclidean distance
        dist = np.linalg.norm(p1 - p2)
        
        # Reading-order bonus: elements that follow in natural reading order
        # (top-to-bottom, left-to-right) get a proximity boost
        reading_order_bonus = 0.0
        if p1[1] < p2[1]:  # elem1 is above elem2
            reading_order_bonus = 0.2
        elif abs(p1[1] - p2[1]) < 20 and p1[0] < p2[0]:  # elem1 is to the left of elem2 on same line
            reading_order_bonus = 0.3
        
        # Normalize distance (assume max doc distance ~1000 for scaling)
        # Closer distance = higher similarity score
        norm_dist = min(dist / 1000.0, 1.0)
        proximity = 1.0 - norm_dist
        
        # Apply reading order bonus (capped at 1.0)
        return min(proximity + reading_order_bonus, 1.0)
    
    def _calculate_formatting_similarity(self, elem1: DocumentElement, elem2: DocumentElement) -> float:
        """
        Calculate similarity based on visual formatting attributes.
        Returns a value in [0,1], where 1 is very similar.
        """
        similarity = 0.5  # Start with neutral similarity
        
        # Headers have strong affinity with content that follows
        if elem1.is_header and not elem2.is_header:
            return 0.9
        
        # Table elements should generally stay together
        if elem1.is_table and elem2.is_table:
            return 0.95
        
        # Same indentation level suggests related content
        if (elem1.indentation_level is not None and 
            elem2.indentation_level is not None and
            elem1.indentation_level == elem2.indentation_level):
            similarity += 0.3
        
        # Similar font suggests related content
        if elem1.font_info and elem2.font_info:
            font1 = elem1.font_info.get('font_name', '')
            font2 = elem2.font_info.get('font_name', '')
            if font1 == font2:
                similarity += 0.1
            
            # Same font size suggests related content
            size1 = elem1.font_info.get('font_size', 0)
            size2 = elem2.font_info.get('font_size', 0)
            if size1 and size2 and abs(size1 - size2) < 2:
                similarity += 0.1
        
        return min(similarity, 1.0)  # Cap at 1.0
    
    def _apply_spectral_clustering(self, graph: nx.Graph, elements: List[DocumentElement]) -> np.ndarray:
        """Apply spectral clustering to the graph."""
        # If graph is empty, return a label for each element
        if graph.number_of_edges() == 0:
            return np.arange(len(elements))
        
        # Create affinity matrix from graph
        affinity = nx.to_numpy_array(graph)
        
        # Determine number of clusters heuristically
        n_elements = len(elements)
        n_clusters = max(
            self.config.min_cluster_size,
            min(n_elements // 5, n_elements // self.config.max_cluster_size + 1)
        )
        
        # Apply spectral clustering
        try:
            clustering = SpectralClustering(
                n_clusters=n_clusters,
                affinity='precomputed',
                assign_labels='discretize',
                random_state=42
            )
            labels = clustering.fit_predict(affinity)
            return labels
        except Exception as e:
            logger.error(f"Spectral clustering failed: {str(e)}")
            # Fallback to connected components
            return self._get_connected_components(graph)
    
    def _apply_agglomerative_clustering(self, graph: nx.Graph, elements: List[DocumentElement]) -> np.ndarray:
        """Apply agglomerative clustering to the graph."""
        # If graph is empty, return a label for each element
        if graph.number_of_edges() == 0:
            return np.arange(len(elements))
        
        # Create a distance matrix (1 - similarity)
        affinity = nx.to_numpy_array(graph)
        distance_matrix = 1 - affinity
        
        # Fill diagonal with 0s (distance to self is 0)
        np.fill_diagonal(distance_matrix, 0)
        
        # Determine number of clusters heuristically
        n_elements = len(elements)
        n_clusters = max(
            self.config.min_cluster_size,
            min(n_elements // 5, n_elements // self.config.max_cluster_size + 1)
        )
        
        # Apply agglomerative clustering
        try:
            clustering = AgglomerativeClustering(
                n_clusters=n_clusters,
                affinity='precomputed',
                linkage='average'
            )
            labels = clustering.fit_predict(distance_matrix)
            return labels
        except Exception as e:
            logger.error(f"Agglomerative clustering failed: {str(e)}")
            # Fallback to connected components
            return self._get_connected_components(graph)
    
    def _get_connected_components(self, graph: nx.Graph) -> np.ndarray:
        """Get connected components from the graph as a fallback clustering method."""
        components = list(nx.connected_components(graph))
        labels = np.zeros(graph.number_of_nodes(), dtype=int)
        
        for i, component in enumerate(components):
            for node in component:
                labels[node] = i
        
        return labels
    
    def langchain_compatible_split(self, documents: List[Document]) -> List[Document]:
        """
        Split documents in a way that's compatible with LangChain.
        Useful when integrating with existing LangChain pipelines.
        
        Args:
            documents: List of LangChain Document objects
            
        Returns:
            List of LangChain Document objects with refined chunking
        """
        # Convert LangChain documents to our format
        elements = []
        for doc in documents:
            # For long documents, use text splitter first
            if len(doc.page_content) > self.config.max_chunk_size * 2:
                chunks = self.text_splitter.split_text(doc.page_content)
                for i, chunk in enumerate(chunks):
                    elements.append(DocumentElement(
                        text_content=chunk,
                        metadata={**doc.metadata, "subchunk_index": i}
                    ))
            else:
                elements.append(DocumentElement(
                    text_content=doc.page_content,
                    metadata=doc.metadata
                ))
        
        # Apply our chunking
        chunks = self.chunk(elements)
        
        # Convert back to LangChain documents
        return [chunk.to_langchain_document() for chunk in chunks]


class ChunkingAgent:
    """
    Specialized agent for document chunking, designed for integration with
    the multi-agent orchestration system.
    
    Features:
    - Hybrid spatial-semantic chunking for complex layouts
    - Integration with LangChain for compatibility
    - Configurable chunking parameters
    - Detailed logging and error handling
    """
    
    def __init__(self, config: Optional[Union[ChunkingConfig, Dict[str, Any]]] = None):
        """
        Initialize the chunking agent.
        
        Args:
            config: ChunkingConfig object or dict with configuration parameters
        """
        self.config = config
        self.chunker = HybridChunker(config)
        logger.info("ChunkingAgent initialized")
        
        # Process stats for monitoring
        self.stats = {
            "documents_processed": 0,
            "chunks_created": 0,
            "avg_processing_time": 0,
            "total_processing_time": 0
        }
    
    def process(self, 
                elements: List[Union[DocumentElement, Dict[str, Any]]],
                document_id: Optional[str] = None) -> List[DocumentChunk]:
        """
        Process document elements into semantically coherent chunks.
        
        Args:
            elements: List of document elements to chunk
            document_id: Optional identifier for the document
            
        Returns:
            List of document chunks
        """
        start_time = time.time()
        
        try:
            # Log processing start
            doc_identifier = document_id or str(uuid.uuid4())
            logger.info(f"Processing document {doc_identifier} with {len(elements)} elements")
            
            # Apply chunking
            chunks = self.chunker.chunk(elements)
            
            # Update metadata with document_id if provided
            if document_id:
                for chunk in chunks:
                    chunk.metadata["document_id"] = document_id
            
            # Update stats
            elapsed_time = time.time() - start_time
            self.stats["documents_processed"] += 1
            self.stats["chunks_created"] += len(chunks)
            self.stats["total_processing_time"] += elapsed_time
            self.stats["avg_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["documents_processed"]
            )
            
            logger.info(f"Chunking completed: {len(chunks)} chunks created in {elapsed_time:.2f} seconds")
            return chunks
            
        except Exception as e:
            logger.error(f"Error in chunking process: {str(e)}", exc_info=True)
            # Return an empty list as fallback
            return []
    
    def process_langchain(self, documents: List[Document]) -> List[Document]:
        """
        Process LangChain documents for compatibility with existing pipelines.
        
        Args:
            documents: List of LangChain Document objects
            
        Returns:
            List of chunked LangChain Document objects
        """
        return self.chunker.langchain_compatible_split(documents)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics."""
        return self.stats
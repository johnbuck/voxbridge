"""
RAG Service Configuration

Settings for embeddings, chunking, retrieval, and database connections.
"""

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class RAGSettings(BaseSettings):
    """RAG service configuration."""

    # Database
    database_url: str = "postgresql+asyncpg://voxbridge:voxbridge_dev_password@postgres:5432/voxbridge"

    # Neo4j (optional)
    neo4j_uri: Optional[str] = None
    neo4j_user: str = "neo4j"
    neo4j_password: str = "voxbridge_graph"

    # LLM for Graphiti entity extraction
    llm_provider: str = "openrouter"  # 'openrouter' or 'local'
    llm_model: Optional[str] = None  # e.g., 'anthropic/claude-3-haiku' or 'llama3.2:3b'

    # Embedding Model
    embedding_model: str = "BAAI/bge-large-en-v1.5"
    embedding_dimension: int = 1024

    # Reranker Model
    reranker_model: str = "BAAI/bge-reranker-base"
    rerank_top_k: int = 10

    # Chunking
    chunk_size: int = 512  # tokens
    chunk_overlap_percent: int = 10

    # Retrieval
    retrieval_top_k: int = 20  # Initial retrieval before reranking
    vector_weight: float = 0.4
    bm25_weight: float = 0.3
    graph_weight: float = 0.3
    rrf_k: int = 60  # RRF constant

    # Service
    host: str = "0.0.0.0"
    port: int = 4910
    debug: bool = False

    # Processing
    max_document_size_mb: int = 50
    supported_extensions: str = ".pdf,.docx,.txt,.md,.html,.csv,.json"

    class Config:
        env_prefix = "RAG_"
        env_file = ".env"
        extra = "ignore"

    @property
    def chunk_overlap(self) -> int:
        """Calculate chunk overlap in tokens."""
        return int(self.chunk_size * self.chunk_overlap_percent / 100)

    @property
    def supported_extensions_list(self) -> list[str]:
        """Get list of supported file extensions."""
        return [ext.strip() for ext in self.supported_extensions.split(",")]


@lru_cache()
def get_settings() -> RAGSettings:
    """Get cached settings instance."""
    return RAGSettings()

"""
Graphiti Knowledge Graph Configuration

Environment-based settings for Graphiti temporal knowledge graph with Neo4j backend.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class GraphitiSettings:
    """Graphiti configuration loaded from environment variables."""

    # Neo4j Connection
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str

    # LLM Provider for Entity Extraction
    llm_provider: str  # "openrouter" | "local" | "openai"
    llm_model: Optional[str]  # Model for entity extraction

    # Embedding Configuration
    embedding_model: str  # e.g., "BAAI/bge-large-en-v1.5"

    # Chunking Configuration
    chunk_size: int  # Number of tokens per chunk
    chunk_overlap: int  # Overlap between chunks (percentage)

    # Reranking Configuration
    reranker_model: str  # e.g., "BAAI/bge-reranker-base"
    rerank_top_k: int  # Number of results after reranking

    # Retrieval Configuration
    retrieval_top_k: int  # Initial retrieval candidates
    use_hybrid_search: bool  # Enable vector + BM25 + graph
    use_temporal_queries: bool  # Enable bi-temporal queries

    @classmethod
    def from_env(cls) -> "GraphitiSettings":
        """Load settings from environment variables."""
        return cls(
            # Neo4j Connection
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "voxbridge_graph"),

            # LLM Provider
            llm_provider=os.getenv("GRAPHITI_LLM_PROVIDER", "openrouter"),
            llm_model=os.getenv("GRAPHITI_LLM_MODEL"),  # Optional override

            # Embedding
            embedding_model=os.getenv(
                "GRAPHITI_EMBEDDING_MODEL",
                "BAAI/bge-large-en-v1.5"
            ),

            # Chunking (512 tokens with 10% overlap - best practice)
            chunk_size=int(os.getenv("GRAPHITI_CHUNK_SIZE", "512")),
            chunk_overlap=int(os.getenv("GRAPHITI_CHUNK_OVERLAP", "10")),

            # Reranking (BGE-reranker-base for <50ms latency)
            reranker_model=os.getenv(
                "GRAPHITI_RERANKER_MODEL",
                "BAAI/bge-reranker-base"
            ),
            rerank_top_k=int(os.getenv("GRAPHITI_RERANK_TOP_K", "5")),

            # Retrieval
            retrieval_top_k=int(os.getenv("GRAPHITI_RETRIEVAL_TOP_K", "30")),
            use_hybrid_search=os.getenv(
                "GRAPHITI_USE_HYBRID_SEARCH", "true"
            ).lower() == "true",
            use_temporal_queries=os.getenv(
                "GRAPHITI_USE_TEMPORAL_QUERIES", "true"
            ).lower() == "true",
        )

    def get_neo4j_config(self) -> dict:
        """Get Neo4j driver configuration."""
        return {
            "uri": self.neo4j_uri,
            "auth": (self.neo4j_user, self.neo4j_password),
        }


# Global settings instance (lazy-loaded)
_settings: GraphitiSettings | None = None


def get_graphiti_settings() -> GraphitiSettings:
    """Get or create the global Graphiti settings instance."""
    global _settings
    if _settings is None:
        _settings = GraphitiSettings.from_env()
    return _settings

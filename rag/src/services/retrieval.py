"""
Hybrid Retrieval Service (RAG Phase 3.1d)

Implements state-of-the-art hybrid retrieval combining:
1. Vector similarity search (pgvector)
2. BM25 keyword search (rank-bm25)
3. Graph traversal (Neo4j/Graphiti)

Results are fused using Reciprocal Rank Fusion (RRF) and
reranked using BGE-reranker-base for maximum accuracy.

Performance targets:
- Retrieval recall@10: >90%
- Reranking latency: <100ms
- End-to-end latency: <500ms
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sentence_transformers import SentenceTransformer
from sqlalchemy import select, text

from ..database.session import get_db_session
from ..database.models import DocumentChunk, Document, Collection, AgentCollection
from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """A single retrieval result with metadata."""

    chunk_id: str
    content: str
    score: float  # Combined score after fusion

    # Source info
    document_id: str
    document_name: str
    collection_id: str
    collection_name: Optional[str] = None

    # Position info
    chunk_index: int = 0
    page_number: Optional[int] = None
    section_title: Optional[str] = None

    # Score breakdown
    vector_score: float = 0.0
    bm25_score: float = 0.0
    graph_score: float = 0.0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResponse:
    """Full retrieval response with results and stats."""

    results: List[RetrievalResult]
    query: str
    total_candidates: int = 0
    retrieval_time_ms: float = 0
    rerank_time_ms: float = 0


class HybridRetrievalService:
    """
    Hybrid retrieval service combining vector, keyword, and graph search.

    Architecture:
    1. Vector Search: pgvector cosine similarity (fast semantic matching)
    2. BM25 Search: Keyword-based ranking (handles exact terms)
    3. Graph Search: Entity-aware traversal (multi-hop reasoning)

    Fusion: Reciprocal Rank Fusion (RRF) combines results
    Reranking: BGE-reranker-base for final relevance scoring

    Usage:
        retriever = HybridRetrievalService()
        await retriever.initialize()
        results = await retriever.retrieve("What is the capital of France?")
    """

    def __init__(self):
        """Initialize retrieval service."""
        self.settings = get_settings()
        self._embedding_model: Optional[SentenceTransformer] = None
        self._reranker = None
        self._bm25_index: Dict[str, Any] = {}  # Collection ID -> BM25 index
        self._graphiti_client = None
        self._initialized = False

    async def initialize(self):
        """Initialize models and connections."""
        if self._initialized:
            return

        # Initialize embedding model
        try:
            logger.info(f"📦 Loading embedding model: {self.settings.embedding_model}")
            self._embedding_model = SentenceTransformer(
                self.settings.embedding_model,
                trust_remote_code=True,
            )
            logger.info("✅ Embedding model loaded")
        except Exception as e:
            logger.error(f"❌ Failed to load embedding model: {e}")
            raise

        # Initialize reranker
        try:
            await self._init_reranker()
        except Exception as e:
            logger.warning(f"⚠️ Reranker unavailable: {e}")

        # Initialize Graphiti (optional)
        try:
            await self._init_graphiti()
        except Exception as e:
            logger.warning(f"⚠️ Graphiti unavailable: {e}")

        self._initialized = True
        logger.info("✅ HybridRetrievalService initialized")

    async def _init_reranker(self):
        """Initialize BGE reranker model."""
        try:
            from FlagEmbedding import FlagReranker

            logger.info(f"📦 Loading reranker: {self.settings.reranker_model}")
            self._reranker = FlagReranker(
                self.settings.reranker_model,
                use_fp16=True,
            )
            logger.info("✅ Reranker loaded")
        except ImportError:
            logger.warning("⚠️ FlagEmbedding not installed, reranking disabled")
            self._reranker = None
        except Exception as e:
            logger.warning(f"⚠️ Reranker loading failed: {e}")
            self._reranker = None

    async def _init_graphiti(self):
        """Initialize Graphiti client for graph search."""
        try:
            from graphiti_core import Graphiti
            from graphiti_core.llm_client import OpenAIClient
            from graphiti_core.llm_client.config import LLMConfig
            import os

            # Configure LLM for entity extraction
            if self.settings.llm_provider == "openrouter":
                llm_config = LLMConfig(
                    api_key=os.getenv("OPENROUTER_API_KEY"),
                    base_url="https://openrouter.ai/api/v1",
                    model=self.settings.llm_model or "anthropic/claude-3-haiku",
                )
            else:
                llm_config = LLMConfig(
                    api_key="not-needed",
                    base_url=os.getenv("LOCAL_LLM_BASE_URL", "http://ollama:11434/v1"),
                    model=self.settings.llm_model or "llama3.2:3b",
                )

            llm_client = OpenAIClient(config=llm_config)

            self._graphiti_client = Graphiti(
                uri=self.settings.neo4j_uri,
                user=self.settings.neo4j_user,
                password=self.settings.neo4j_password,
                llm_client=llm_client,
            )
            logger.info("✅ Graphiti connected for graph search")
        except Exception as e:
            logger.warning(f"⚠️ Graphiti connection failed: {e}")
            self._graphiti_client = None

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for query text."""
        if not self._embedding_model:
            raise RuntimeError("Embedding model not initialized")

        embedding = self._embedding_model.encode(
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()

    async def retrieve(
        self,
        query: str,
        collection_ids: Optional[List[UUID]] = None,
        agent_id: Optional[UUID] = None,
        top_k: int = 10,
        use_reranking: bool = True,
        use_graph: bool = True,
    ) -> RetrievalResponse:
        """
        Retrieve relevant chunks using hybrid search.

        Args:
            query: Search query
            collection_ids: Optional specific collections to search
            agent_id: Optional agent ID (uses agent's linked collections)
            top_k: Number of results to return
            use_reranking: Whether to apply reranking
            use_graph: Whether to include graph search

        Returns:
            RetrievalResponse with ranked results
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()

        # Get collection IDs if agent specified
        if agent_id and not collection_ids:
            collection_ids = await self._get_agent_collections(agent_id)

        # Run parallel searches
        retrieval_top_k = self.settings.retrieval_top_k  # Get more candidates for fusion

        search_tasks = [
            self._vector_search(query, collection_ids, retrieval_top_k),
            self._bm25_search(query, collection_ids, retrieval_top_k),
        ]

        if use_graph and self._graphiti_client:
            search_tasks.append(self._graph_search(query, collection_ids, retrieval_top_k))

        results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Collect valid results
        vector_results = results[0] if not isinstance(results[0], Exception) else []
        bm25_results = results[1] if not isinstance(results[1], Exception) else []
        graph_results = results[2] if len(results) > 2 and not isinstance(results[2], Exception) else []

        # Log any errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Search {i} failed: {result}")

        retrieval_time = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Fuse results using RRF
        total_candidates = len(set(
            r["chunk_id"] for r in vector_results + bm25_results + graph_results
        ))

        fused_results = self._reciprocal_rank_fusion(
            vector_results=vector_results,
            bm25_results=bm25_results,
            graph_results=graph_results,
        )

        # Apply reranking if available
        rerank_time = 0
        if use_reranking and self._reranker and fused_results:
            rerank_start = datetime.utcnow()
            fused_results = await self._rerank_results(query, fused_results)
            rerank_time = (datetime.utcnow() - rerank_start).total_seconds() * 1000

        # Take top_k results
        final_results = fused_results[:top_k]

        logger.info(
            f"🔍 Retrieved {len(final_results)}/{total_candidates} results "
            f"(retrieval: {retrieval_time:.0f}ms, rerank: {rerank_time:.0f}ms)"
        )

        return RetrievalResponse(
            results=final_results,
            query=query,
            total_candidates=total_candidates,
            retrieval_time_ms=retrieval_time,
            rerank_time_ms=rerank_time,
        )

    async def _get_agent_collections(self, agent_id: UUID) -> List[UUID]:
        """Get collection IDs linked to an agent."""
        async with get_db_session() as db:
            result = await db.execute(
                select(AgentCollection.collection_id)
                .where(AgentCollection.agent_id == agent_id)
                .order_by(AgentCollection.priority.desc())
            )
            return [row[0] for row in result.fetchall()]

    async def _vector_search(
        self,
        query: str,
        collection_ids: Optional[List[UUID]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Perform vector similarity search using pgvector."""
        query_embedding = self._generate_embedding(query)

        async with get_db_session() as db:
            # Build collection filter
            collection_filter = ""
            params = {
                "query_embedding": query_embedding,
                "limit": limit,
            }

            if collection_ids:
                collection_filter = "AND d.collection_id = ANY(:collection_ids)"
                params["collection_ids"] = [str(cid) for cid in collection_ids]

            result = await db.execute(
                text(f"""
                    SELECT
                        dc.id::text as chunk_id,
                        dc.content,
                        dc.chunk_index,
                        dc.page_number,
                        dc.section_title,
                        dc.metadata,
                        d.id::text as document_id,
                        d.filename as document_name,
                        d.collection_id::text as collection_id,
                        c.name as collection_name,
                        1 - (dc.embedding <=> :query_embedding::vector) AS score
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    JOIN collections c ON d.collection_id = c.id
                    WHERE dc.embedding IS NOT NULL
                    {collection_filter}
                    ORDER BY dc.embedding <=> :query_embedding::vector
                    LIMIT :limit
                """),
                params
            )

            rows = result.fetchall()

            return [
                {
                    "chunk_id": row.chunk_id,
                    "content": row.content,
                    "chunk_index": row.chunk_index,
                    "page_number": row.page_number,
                    "section_title": row.section_title,
                    "metadata": row.metadata or {},
                    "document_id": row.document_id,
                    "document_name": row.document_name,
                    "collection_id": row.collection_id,
                    "collection_name": row.collection_name,
                    "vector_score": float(row.score),
                }
                for row in rows
            ]

    async def _bm25_search(
        self,
        query: str,
        collection_ids: Optional[List[UUID]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Perform BM25 keyword search."""
        from rank_bm25 import BM25Okapi
        import re

        # Get chunks from database
        async with get_db_session() as db:
            collection_filter = ""
            params = {}

            if collection_ids:
                collection_filter = "WHERE d.collection_id = ANY(:collection_ids)"
                params["collection_ids"] = [str(cid) for cid in collection_ids]

            result = await db.execute(
                text(f"""
                    SELECT
                        dc.id::text as chunk_id,
                        dc.content,
                        dc.chunk_index,
                        dc.page_number,
                        dc.section_title,
                        dc.metadata,
                        d.id::text as document_id,
                        d.filename as document_name,
                        d.collection_id::text as collection_id,
                        c.name as collection_name
                    FROM document_chunks dc
                    JOIN documents d ON dc.document_id = d.id
                    JOIN collections c ON d.collection_id = c.id
                    {collection_filter}
                """),
                params
            )

            chunks = result.fetchall()

        if not chunks:
            return []

        # Tokenize documents
        def tokenize(text: str) -> List[str]:
            return re.findall(r'\w+', text.lower())

        corpus = [tokenize(chunk.content) for chunk in chunks]
        query_tokens = tokenize(query)

        # Create BM25 index
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)

        # Combine with chunk data
        results = []
        for i, (chunk, score) in enumerate(zip(chunks, scores)):
            if score > 0:
                results.append({
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                    "page_number": chunk.page_number,
                    "section_title": chunk.section_title,
                    "metadata": chunk.metadata or {},
                    "document_id": chunk.document_id,
                    "document_name": chunk.document_name,
                    "collection_id": chunk.collection_id,
                    "collection_name": chunk.collection_name,
                    "bm25_score": float(score),
                })

        # Sort by score and limit
        results.sort(key=lambda x: x["bm25_score"], reverse=True)
        return results[:limit]

    async def _graph_search(
        self,
        query: str,
        collection_ids: Optional[List[UUID]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Perform graph-based search using Graphiti."""
        if not self._graphiti_client:
            return []

        try:
            # Search graph for relevant entities/facts
            graph_results = await self._graphiti_client.search(
                query=query,
                num_results=limit,
            )

            results = []
            for result in graph_results:
                # Extract chunk references if available
                if hasattr(result, 'source_description'):
                    results.append({
                        "chunk_id": getattr(result, 'uuid', 'graph_result'),
                        "content": str(result),
                        "chunk_index": 0,
                        "page_number": None,
                        "section_title": None,
                        "metadata": {"source": "graph"},
                        "document_id": "graph",
                        "document_name": "Knowledge Graph",
                        "collection_id": "graph",
                        "collection_name": "Knowledge Graph",
                        "graph_score": getattr(result, 'score', 0.5),
                    })

            return results

        except Exception as e:
            logger.warning(f"⚠️ Graph search failed: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        vector_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        graph_results: List[Dict[str, Any]],
        k: int = 60,  # RRF constant
    ) -> List[RetrievalResult]:
        """
        Fuse results using Reciprocal Rank Fusion (RRF).

        RRF score = sum(1 / (k + rank)) for each result list

        Args:
            vector_results: Results from vector search
            bm25_results: Results from BM25 search
            graph_results: Results from graph search
            k: RRF constant (default 60)

        Returns:
            List of fused RetrievalResults sorted by score
        """
        # Calculate RRF scores
        rrf_scores: Dict[str, Dict[str, Any]] = {}

        # Process vector results
        for rank, result in enumerate(vector_results, 1):
            chunk_id = result["chunk_id"]
            if chunk_id not in rrf_scores:
                rrf_scores[chunk_id] = {
                    **result,
                    "rrf_score": 0,
                    "vector_score": 0,
                    "bm25_score": 0,
                    "graph_score": 0,
                }
            rrf_scores[chunk_id]["rrf_score"] += 1 / (k + rank)
            rrf_scores[chunk_id]["vector_score"] = result.get("vector_score", 0)

        # Process BM25 results
        for rank, result in enumerate(bm25_results, 1):
            chunk_id = result["chunk_id"]
            if chunk_id not in rrf_scores:
                rrf_scores[chunk_id] = {
                    **result,
                    "rrf_score": 0,
                    "vector_score": 0,
                    "bm25_score": 0,
                    "graph_score": 0,
                }
            rrf_scores[chunk_id]["rrf_score"] += 1 / (k + rank)
            rrf_scores[chunk_id]["bm25_score"] = result.get("bm25_score", 0)

        # Process graph results
        for rank, result in enumerate(graph_results, 1):
            chunk_id = result["chunk_id"]
            if chunk_id not in rrf_scores:
                rrf_scores[chunk_id] = {
                    **result,
                    "rrf_score": 0,
                    "vector_score": 0,
                    "bm25_score": 0,
                    "graph_score": 0,
                }
            rrf_scores[chunk_id]["rrf_score"] += 1 / (k + rank)
            rrf_scores[chunk_id]["graph_score"] = result.get("graph_score", 0)

        # Convert to RetrievalResult objects
        results = []
        for chunk_id, data in rrf_scores.items():
            results.append(RetrievalResult(
                chunk_id=chunk_id,
                content=data["content"],
                score=data["rrf_score"],
                document_id=data["document_id"],
                document_name=data["document_name"],
                collection_id=data["collection_id"],
                collection_name=data.get("collection_name"),
                chunk_index=data.get("chunk_index", 0),
                page_number=data.get("page_number"),
                section_title=data.get("section_title"),
                vector_score=data["vector_score"],
                bm25_score=data["bm25_score"],
                graph_score=data["graph_score"],
                metadata=data.get("metadata", {}),
            ))

        # Sort by RRF score
        results.sort(key=lambda x: x.score, reverse=True)

        return results

    async def _rerank_results(
        self,
        query: str,
        results: List[RetrievalResult],
    ) -> List[RetrievalResult]:
        """Rerank results using BGE-reranker-base."""
        if not self._reranker or not results:
            return results

        try:
            # Prepare pairs for reranking
            pairs = [[query, r.content] for r in results]

            # Get reranker scores
            scores = self._reranker.compute_score(pairs)

            # Handle single result case
            if isinstance(scores, (int, float)):
                scores = [scores]

            # Update scores
            for result, score in zip(results, scores):
                result.score = float(score)

            # Re-sort by new scores
            results.sort(key=lambda x: x.score, reverse=True)

            return results

        except Exception as e:
            logger.warning(f"⚠️ Reranking failed: {e}")
            return results

    async def close(self):
        """Close connections."""
        if self._graphiti_client:
            try:
                await self._graphiti_client.close()
            except Exception:
                pass
        self._initialized = False


# Singleton instance
_retrieval_service: Optional[HybridRetrievalService] = None


async def get_retrieval_service() -> HybridRetrievalService:
    """Get or create the singleton retrieval service."""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = HybridRetrievalService()
        await _retrieval_service.initialize()
    return _retrieval_service

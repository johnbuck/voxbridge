"""
Retrieval API Routes (RAG Phase 3.1d)

FastAPI routes for knowledge retrieval and search.
Exposes hybrid retrieval (vector + BM25 + graph) to agents and frontend.
"""

import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field

from ..services.retrieval import get_retrieval_service, RetrievalResult, RetrievalResponse
from ..services.citations import get_citation_service, Citation

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================


class SearchRequest(BaseModel):
    """Request body for knowledge search."""

    query: str = Field(..., min_length=1, max_length=2000, description="Search query")
    collection_ids: Optional[List[str]] = Field(None, description="Collection UUIDs to search")
    agent_id: Optional[str] = Field(None, description="Agent UUID (uses linked collections)")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    use_reranking: bool = Field(True, description="Apply cross-encoder reranking")
    use_graph: bool = Field(True, description="Include graph search")
    include_citations: bool = Field(True, description="Generate citations for results")


class SearchResultResponse(BaseModel):
    """Response model for a single search result."""

    chunk_id: str
    content: str
    score: float
    document_id: str
    document_name: str
    collection_id: str
    collection_name: Optional[str]
    chunk_index: int
    page_number: Optional[int]
    section_title: Optional[str]
    vector_score: float
    bm25_score: float
    graph_score: float


class CitationResponse(BaseModel):
    """Response model for a citation."""

    index: int
    document_name: str
    collection_name: Optional[str]
    page_number: Optional[int]
    section_title: Optional[str]
    relevance_score: float
    excerpt: str
    chunk_id: Optional[str]
    document_id: Optional[str]


class SearchResponse(BaseModel):
    """Full search response."""

    results: List[SearchResultResponse]
    citations: Optional[List[CitationResponse]]
    query: str
    total_candidates: int
    retrieval_time_ms: float
    rerank_time_ms: float


class ContextRequest(BaseModel):
    """Request body for generating LLM context."""

    query: str = Field(..., min_length=1, max_length=2000, description="Query for context retrieval")
    collection_ids: Optional[List[str]] = Field(None, description="Collection UUIDs")
    agent_id: Optional[str] = Field(None, description="Agent UUID")
    max_results: int = Field(5, ge=1, le=20, description="Maximum results to include in context")
    include_citations: bool = Field(True, description="Include citation markers in context")


class ContextResponse(BaseModel):
    """Response with formatted LLM context."""

    context: str = Field(..., description="Formatted context for LLM prompt")
    sources_count: int = Field(..., description="Number of sources included")
    retrieval_time_ms: float


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ============================================================================
# Search Routes
# ============================================================================


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Search Knowledge Base",
    description="Perform hybrid search across document collections"
)
async def search_knowledge(request: SearchRequest):
    """
    Search the knowledge base using hybrid retrieval.

    Combines:
    - Vector similarity search (semantic matching)
    - BM25 keyword search (exact term matching)
    - Graph traversal (entity relationships)

    Results are fused using Reciprocal Rank Fusion (RRF)
    and optionally reranked using BGE-reranker-base.
    """
    try:
        retrieval_service = await get_retrieval_service()

        # Parse collection IDs
        collection_ids = None
        if request.collection_ids:
            collection_ids = [UUID(cid) for cid in request.collection_ids]

        agent_id = UUID(request.agent_id) if request.agent_id else None

        # Perform search
        response = await retrieval_service.retrieve(
            query=request.query,
            collection_ids=collection_ids,
            agent_id=agent_id,
            top_k=request.top_k,
            use_reranking=request.use_reranking,
            use_graph=request.use_graph,
        )

        # Generate citations if requested
        citations = None
        if request.include_citations:
            citation_service = get_citation_service()
            citation_list = citation_service.generate_citations(
                results=response.results,
                query=request.query,
            )
            citations = [
                CitationResponse(
                    index=c.index,
                    document_name=c.document_name,
                    collection_name=c.collection_name,
                    page_number=c.page_number,
                    section_title=c.section_title,
                    relevance_score=c.relevance_score,
                    excerpt=c.excerpt,
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                )
                for c in citation_list
            ]

        return SearchResponse(
            results=[
                SearchResultResponse(
                    chunk_id=r.chunk_id,
                    content=r.content,
                    score=r.score,
                    document_id=r.document_id,
                    document_name=r.document_name,
                    collection_id=r.collection_id,
                    collection_name=r.collection_name,
                    chunk_index=r.chunk_index,
                    page_number=r.page_number,
                    section_title=r.section_title,
                    vector_score=r.vector_score,
                    bm25_score=r.bm25_score,
                    graph_score=r.graph_score,
                )
                for r in response.results
            ],
            citations=citations,
            query=response.query,
            total_candidates=response.total_candidates,
            retrieval_time_ms=response.retrieval_time_ms,
            rerank_time_ms=response.rerank_time_ms,
        )

    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}"
        )


@router.get(
    "/search",
    response_model=SearchResponse,
    summary="Search Knowledge Base (GET)",
    description="Simple GET-based search for quick queries"
)
async def search_knowledge_get(
    query: str = Query(..., min_length=1, max_length=500, description="Search query"),
    collection_id: Optional[str] = Query(None, description="Single collection UUID"),
    agent_id: Optional[str] = Query(None, description="Agent UUID"),
    top_k: int = Query(10, ge=1, le=50, description="Number of results"),
):
    """
    Simple GET-based search endpoint.

    Use the POST endpoint for more control over search parameters.
    """
    request = SearchRequest(
        query=query,
        collection_ids=[collection_id] if collection_id else None,
        agent_id=agent_id,
        top_k=top_k,
    )
    return await search_knowledge(request)


@router.post(
    "/context",
    response_model=ContextResponse,
    summary="Generate LLM Context",
    description="Retrieve and format context for LLM prompts"
)
async def generate_context(request: ContextRequest):
    """
    Generate formatted context for LLM prompts.

    Retrieves relevant documents and formats them with citation markers
    that the LLM can reference in its response.

    This endpoint is designed for integration with the LLM service
    to enable RAG-augmented responses.
    """
    try:
        retrieval_service = await get_retrieval_service()
        citation_service = get_citation_service()

        # Parse collection IDs
        collection_ids = None
        if request.collection_ids:
            collection_ids = [UUID(cid) for cid in request.collection_ids]

        agent_id = UUID(request.agent_id) if request.agent_id else None

        # Perform search
        response = await retrieval_service.retrieve(
            query=request.query,
            collection_ids=collection_ids,
            agent_id=agent_id,
            top_k=request.max_results,
            use_reranking=True,
            use_graph=True,
        )

        # Format as LLM context
        context = citation_service.format_context_for_llm(
            results=response.results,
            include_citations=request.include_citations,
        )

        return ContextResponse(
            context=context,
            sources_count=len(response.results),
            retrieval_time_ms=response.retrieval_time_ms + response.rerank_time_ms,
        )

    except Exception as e:
        logger.error(f"❌ Context generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context generation failed: {str(e)}"
        )


# ============================================================================
# Agent-Specific Routes
# ============================================================================


@router.get(
    "/agents/{agent_id}/search",
    response_model=SearchResponse,
    summary="Search Agent's Knowledge",
    description="Search collections linked to a specific agent"
)
async def search_agent_knowledge(
    agent_id: UUID,
    query: str = Query(..., min_length=1, max_length=500),
    top_k: int = Query(10, ge=1, le=50),
):
    """
    Search knowledge base for a specific agent.

    Only searches collections that are linked to the agent
    via the agent_collections table.
    """
    request = SearchRequest(
        query=query,
        agent_id=str(agent_id),
        top_k=top_k,
    )
    return await search_knowledge(request)


@router.post(
    "/agents/{agent_id}/context",
    response_model=ContextResponse,
    summary="Generate Agent Context",
    description="Generate RAG context for an agent's LLM calls"
)
async def generate_agent_context(
    agent_id: UUID,
    request: ContextRequest,
):
    """
    Generate RAG context for an agent.

    This endpoint is called by the LLM service before generating responses
    to inject relevant knowledge into the agent's context window.
    """
    # Override agent_id from path
    request.agent_id = str(agent_id)
    return await generate_context(request)


# ============================================================================
# Health & Stats Routes
# ============================================================================


@router.get(
    "/health",
    summary="Knowledge System Health",
    description="Check health of retrieval system components"
)
async def knowledge_health():
    """
    Check health of knowledge system components.

    Returns status of:
    - Embedding model
    - Reranker model
    - Graphiti/Neo4j connection
    """
    try:
        retrieval_service = await get_retrieval_service()

        return {
            "status": "healthy",
            "components": {
                "embedding_model": retrieval_service._embedding_model is not None,
                "reranker": retrieval_service._reranker is not None,
                "graphiti": retrieval_service._graphiti_client is not None,
            },
            "settings": {
                "embedding_model": retrieval_service.settings.embedding_model,
                "reranker_model": retrieval_service.settings.reranker_model,
                "retrieval_top_k": retrieval_service.settings.retrieval_top_k,
                "rerank_top_k": retrieval_service.settings.rerank_top_k,
            },
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }

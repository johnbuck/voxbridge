"""
RAG Proxy Routes (Phase 3.1 Containerization)

FastAPI routes that proxy RAG requests to the voxbridge-rag service.
Maintains API compatibility while delegating to the dedicated RAG container.
"""

import logging
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from src.services.rag_client import get_rag_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["RAG"])


# ============================================================================
# Request/Response Models (same as original for API compatibility)
# ============================================================================


class CollectionCreateRequest(BaseModel):
    """Request body for creating a collection"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    is_public: bool = Field(False)
    metadata: Optional[dict] = None


class CollectionUpdateRequest(BaseModel):
    """Request body for updating a collection"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    is_public: Optional[bool] = None
    metadata: Optional[dict] = None


class AgentCollectionRequest(BaseModel):
    """Request body for assigning collection to agent"""
    collection_id: UUID
    priority: int = Field(0, ge=0)


class WebIngestRequest(BaseModel):
    """Request body for web page ingestion"""
    url: str
    depth: int = Field(0, ge=0, le=3)
    metadata: Optional[dict] = None


class SearchRequest(BaseModel):
    """Request body for hybrid search"""
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=100)
    include_graph: bool = Field(True)
    min_score: float = Field(0.0, ge=0.0, le=1.0)


class ContextRequest(BaseModel):
    """Request body for LLM context generation"""
    query: str = Field(..., min_length=1)
    max_tokens: int = Field(2000, ge=100, le=8000)


# ============================================================================
# Collection Routes (Proxy)
# ============================================================================


@router.get("/collections")
async def list_collections(
    user_id: Optional[UUID] = Query(None),
    include_public: bool = Query(True)
):
    """List all collections for a user (including public ones)"""
    try:
        client = get_rag_client()
        return await client.list_collections(user_id=user_id, include_public=include_public)
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.post("/collections", status_code=status.HTTP_201_CREATED)
async def create_collection(request: CollectionCreateRequest, user_id: UUID = Query(...)):
    """Create a new collection"""
    try:
        client = get_rag_client()
        return await client.create_collection(
            name=request.name,
            user_id=user_id,
            description=request.description,
            is_public=request.is_public,
            metadata=request.metadata
        )
    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.get("/collections/{collection_id}")
async def get_collection(collection_id: UUID):
    """Get collection details"""
    try:
        client = get_rag_client()
        return await client.get_collection(collection_id)
    except Exception as e:
        logger.error(f"Failed to get collection: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.patch("/collections/{collection_id}")
async def update_collection(collection_id: UUID, request: CollectionUpdateRequest):
    """Update a collection"""
    try:
        client = get_rag_client()
        return await client.update_collection(
            collection_id=collection_id,
            name=request.name,
            description=request.description,
            is_public=request.is_public,
            metadata=request.metadata
        )
    except Exception as e:
        logger.error(f"Failed to update collection: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.delete("/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(collection_id: UUID):
    """Delete a collection and all its documents"""
    try:
        client = get_rag_client()
        await client.delete_collection(collection_id)
    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


# ============================================================================
# Document Routes (Proxy)
# ============================================================================


@router.get("/collections/{collection_id}/documents")
async def list_documents(
    collection_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """List documents in a collection"""
    try:
        client = get_rag_client()
        return await client.list_documents(collection_id, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.post("/collections/{collection_id}/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    collection_id: UUID,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None)
):
    """Upload a document to a collection (async processing)"""
    try:
        client = get_rag_client()
        content = await file.read()
        meta_dict = None
        if metadata:
            import json
            try:
                meta_dict = json.loads(metadata)
            except json.JSONDecodeError:
                pass

        return await client.ingest_document(
            collection_id=collection_id,
            file_content=content,
            filename=file.filename,
            mime_type=file.content_type,
            metadata=meta_dict
        )
    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.post("/collections/{collection_id}/web", status_code=status.HTTP_202_ACCEPTED)
async def ingest_web_page(collection_id: UUID, request: WebIngestRequest):
    """Ingest a web page into a collection"""
    try:
        client = get_rag_client()
        return await client.ingest_web(
            collection_id=collection_id,
            url=request.url,
            depth=request.depth,
            metadata=request.metadata
        )
    except Exception as e:
        logger.error(f"Failed to ingest web page: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.get("/documents/{document_id}")
async def get_document(document_id: UUID):
    """Get document details with chunk preview"""
    try:
        client = get_rag_client()
        return await client.get_document(document_id)
    except Exception as e:
        logger.error(f"Failed to get document: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID):
    """Delete a document and its chunks"""
    try:
        client = get_rag_client()
        await client.delete_document(document_id)
    except Exception as e:
        logger.error(f"Failed to delete document: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


# ============================================================================
# Agent-Collection Routes (Proxy)
# ============================================================================


@router.get("/agents/{agent_id}/collections")
async def get_agent_collections(agent_id: UUID):
    """Get all collections assigned to an agent"""
    try:
        client = get_rag_client()
        return await client.get_agent_collections(agent_id)
    except Exception as e:
        logger.error(f"Failed to get agent collections: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.post("/agents/{agent_id}/collections", status_code=status.HTTP_201_CREATED)
async def assign_collection_to_agent(agent_id: UUID, request: AgentCollectionRequest):
    """Assign a collection to an agent"""
    try:
        client = get_rag_client()
        return await client.assign_collection_to_agent(
            agent_id=agent_id,
            collection_id=request.collection_id,
            priority=request.priority
        )
    except Exception as e:
        logger.error(f"Failed to assign collection: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.delete("/agents/{agent_id}/collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_collection_from_agent(agent_id: UUID, collection_id: UUID):
    """Remove a collection assignment from an agent"""
    try:
        client = get_rag_client()
        await client.remove_collection_from_agent(agent_id, collection_id)
    except Exception as e:
        logger.error(f"Failed to remove collection assignment: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


# ============================================================================
# Search & Retrieval Routes (Proxy)
# ============================================================================


@router.post("/knowledge/search")
async def search(
    request: SearchRequest,
    agent_id: UUID = Query(...),
    user_id: Optional[UUID] = Query(None)
):
    """Hybrid search across agent's knowledge collections"""
    try:
        client = get_rag_client()
        result = await client.search(
            query=request.query,
            agent_id=agent_id,
            user_id=user_id,
            top_k=request.top_k,
            include_graph=request.include_graph,
            min_score=request.min_score
        )
        return {
            "query": result.query,
            "results": [
                {
                    "content": r.content,
                    "score": r.score,
                    "document_id": r.document_id,
                    "chunk_id": r.chunk_id,
                    "metadata": r.metadata,
                    "citation": r.citation
                }
                for r in result.results
            ],
            "total_results": result.total_results,
            "search_time_ms": result.search_time_ms
        }
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.post("/knowledge/context")
async def get_context(
    request: ContextRequest,
    agent_id: UUID = Query(...),
    user_id: Optional[UUID] = Query(None)
):
    """Get formatted context for LLM prompt augmentation"""
    try:
        client = get_rag_client()
        result = await client.get_context(
            query=request.query,
            agent_id=agent_id,
            user_id=user_id,
            max_tokens=request.max_tokens
        )
        return {
            "query": result.query,
            "context": result.context,
            "sources": result.sources
        }
    except Exception as e:
        logger.error(f"Context generation failed: {e}")
        raise HTTPException(status_code=503, detail=f"RAG service error: {str(e)}")


@router.get("/knowledge/health")
async def rag_health():
    """Check RAG service health"""
    try:
        client = get_rag_client()
        return await client.health_check()
    except Exception as e:
        logger.error(f"RAG health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}

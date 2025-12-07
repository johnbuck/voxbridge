"""
VoxBridge RAG Client

HTTP client for communicating with the voxbridge-rag service.
Provides async methods for document ingestion, search, and collection management.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from uuid import UUID
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

# RAG service configuration
RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://voxbridge-rag:4910")
RAG_TIMEOUT = float(os.getenv("RAG_TIMEOUT", "60.0"))


@dataclass
class RetrievalResult:
    """A single retrieval result from the RAG service."""
    content: str
    score: float
    document_id: str
    chunk_id: str
    metadata: Dict[str, Any]
    citation: Optional[str] = None


@dataclass
class SearchResponse:
    """Response from the RAG search endpoint."""
    results: List[RetrievalResult]
    query: str
    total_results: int
    search_time_ms: float


@dataclass
class ContextResponse:
    """Response from the RAG context endpoint."""
    context: str
    sources: List[Dict[str, Any]]
    query: str


class RAGClient:
    """
    Async HTTP client for the VoxBridge RAG service.

    Handles:
    - Document ingestion (files and web pages)
    - Hybrid search (vector + BM25 + graph)
    - LLM context generation
    - Collection management
    """

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[float] = None):
        """
        Initialize the RAG client.

        Args:
            base_url: RAG service URL. Defaults to RAG_SERVICE_URL env var.
            timeout: Request timeout in seconds. Defaults to RAG_TIMEOUT env var.
        """
        self.base_url = (base_url or RAG_SERVICE_URL).rstrip("/")
        self.timeout = timeout or RAG_TIMEOUT
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"}
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # Health Check

    async def health_check(self) -> Dict[str, Any]:
        """
        Check RAG service health.

        Returns:
            Health status including database, Neo4j, and retrieval service status.
        """
        try:
            client = await self._get_client()
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"RAG health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    # Search & Retrieval

    async def search(
        self,
        query: str,
        agent_id: UUID,
        user_id: Optional[UUID] = None,
        top_k: int = 10,
        include_graph: bool = True,
        min_score: float = 0.0
    ) -> SearchResponse:
        """
        Perform hybrid search across agent's knowledge collections.

        Args:
            query: Search query text.
            agent_id: Agent UUID to search collections for.
            user_id: Optional user UUID for filtering.
            top_k: Maximum number of results to return.
            include_graph: Whether to include graph traversal results.
            min_score: Minimum relevance score threshold.

        Returns:
            SearchResponse with ranked results.
        """
        client = await self._get_client()

        payload = {
            "query": query,
            "agent_id": str(agent_id),
            "top_k": top_k,
            "include_graph": include_graph,
            "min_score": min_score
        }
        if user_id:
            payload["user_id"] = str(user_id)

        response = await client.post("/search", json=payload)
        response.raise_for_status()
        data = response.json()

        results = [
            RetrievalResult(
                content=r["content"],
                score=r["score"],
                document_id=r["document_id"],
                chunk_id=r["chunk_id"],
                metadata=r.get("metadata", {}),
                citation=r.get("citation")
            )
            for r in data.get("results", [])
        ]

        return SearchResponse(
            results=results,
            query=data["query"],
            total_results=data.get("total_results", len(results)),
            search_time_ms=data.get("search_time_ms", 0.0)
        )

    async def get_context(
        self,
        query: str,
        agent_id: UUID,
        user_id: Optional[UUID] = None,
        max_tokens: int = 2000
    ) -> ContextResponse:
        """
        Get formatted context for LLM prompt augmentation.

        Args:
            query: Query to generate context for.
            agent_id: Agent UUID.
            user_id: Optional user UUID.
            max_tokens: Maximum tokens for context.

        Returns:
            ContextResponse with formatted context and sources.
        """
        client = await self._get_client()

        payload = {
            "query": query,
            "agent_id": str(agent_id),
            "max_tokens": max_tokens
        }
        if user_id:
            payload["user_id"] = str(user_id)

        response = await client.post("/context", json=payload)
        response.raise_for_status()
        data = response.json()

        return ContextResponse(
            context=data["context"],
            sources=data.get("sources", []),
            query=data["query"]
        )

    # Document Ingestion

    async def ingest_document(
        self,
        collection_id: UUID,
        file_content: bytes,
        filename: str,
        mime_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ingest a document file into a collection.

        Args:
            collection_id: Target collection UUID.
            file_content: Raw file bytes.
            filename: Original filename.
            mime_type: MIME type (auto-detected if not provided).
            metadata: Optional document metadata.

        Returns:
            Document record with processing status.
        """
        client = await self._get_client()

        # Use multipart form for file upload
        files = {"file": (filename, file_content, mime_type or "application/octet-stream")}
        data = {"collection_id": str(collection_id)}
        if metadata:
            data["metadata"] = str(metadata)

        response = await client.post(
            "/ingest",
            files=files,
            data=data,
            headers={}  # Let httpx set multipart headers
        )
        response.raise_for_status()
        return response.json()

    async def ingest_web(
        self,
        collection_id: UUID,
        url: str,
        depth: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Ingest a web page into a collection.

        Args:
            collection_id: Target collection UUID.
            url: Web page URL to scrape.
            depth: Link following depth (0 = single page).
            metadata: Optional document metadata.

        Returns:
            Document record with processing status.
        """
        client = await self._get_client()

        payload = {
            "collection_id": str(collection_id),
            "url": url,
            "depth": depth
        }
        if metadata:
            payload["metadata"] = metadata

        response = await client.post("/ingest/web", json=payload)
        response.raise_for_status()
        return response.json()

    # Collection Management

    async def list_collections(
        self,
        user_id: Optional[UUID] = None,
        include_public: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List available collections.

        Args:
            user_id: Filter by owner user ID.
            include_public: Whether to include public collections.

        Returns:
            List of collection records.
        """
        client = await self._get_client()

        params = {"include_public": str(include_public).lower()}
        if user_id:
            params["user_id"] = str(user_id)

        response = await client.get("/collections", params=params)
        response.raise_for_status()
        return response.json()

    async def get_collection(self, collection_id: UUID) -> Dict[str, Any]:
        """
        Get a specific collection by ID.

        Args:
            collection_id: Collection UUID.

        Returns:
            Collection record with statistics.
        """
        client = await self._get_client()
        response = await client.get(f"/collections/{collection_id}")
        response.raise_for_status()
        return response.json()

    async def create_collection(
        self,
        name: str,
        user_id: UUID,
        description: Optional[str] = None,
        is_public: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new collection.

        Args:
            name: Collection name.
            user_id: Owner user ID.
            description: Optional description.
            is_public: Whether collection is publicly accessible.
            metadata: Optional metadata.

        Returns:
            Created collection record.
        """
        client = await self._get_client()

        payload = {
            "name": name,
            "user_id": str(user_id),
            "is_public": is_public
        }
        if description:
            payload["description"] = description
        if metadata:
            payload["metadata"] = metadata

        response = await client.post("/collections", json=payload)
        response.raise_for_status()
        return response.json()

    async def update_collection(
        self,
        collection_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_public: Optional[bool] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update a collection.

        Args:
            collection_id: Collection UUID.
            name: New name (optional).
            description: New description (optional).
            is_public: New visibility (optional).
            metadata: New metadata (optional).

        Returns:
            Updated collection record.
        """
        client = await self._get_client()

        payload = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if is_public is not None:
            payload["is_public"] = is_public
        if metadata is not None:
            payload["metadata"] = metadata

        response = await client.patch(f"/collections/{collection_id}", json=payload)
        response.raise_for_status()
        return response.json()

    async def delete_collection(self, collection_id: UUID) -> bool:
        """
        Delete a collection and all its documents.

        Args:
            collection_id: Collection UUID.

        Returns:
            True if deleted successfully.
        """
        client = await self._get_client()
        response = await client.delete(f"/collections/{collection_id}")
        response.raise_for_status()
        return True

    # Document Management

    async def list_documents(
        self,
        collection_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List documents in a collection.

        Args:
            collection_id: Collection UUID.
            limit: Maximum documents to return.
            offset: Pagination offset.

        Returns:
            List of document records.
        """
        client = await self._get_client()

        params = {"limit": limit, "offset": offset}
        response = await client.get(f"/collections/{collection_id}/documents", params=params)
        response.raise_for_status()
        return response.json()

    async def get_document(self, document_id: UUID) -> Dict[str, Any]:
        """
        Get a specific document by ID.

        Args:
            document_id: Document UUID.

        Returns:
            Document record with chunks.
        """
        client = await self._get_client()
        response = await client.get(f"/documents/{document_id}")
        response.raise_for_status()
        return response.json()

    async def delete_document(self, document_id: UUID) -> bool:
        """
        Delete a document and its chunks.

        Args:
            document_id: Document UUID.

        Returns:
            True if deleted successfully.
        """
        client = await self._get_client()
        response = await client.delete(f"/documents/{document_id}")
        response.raise_for_status()
        return True

    # Agent-Collection Assignments

    async def assign_collection_to_agent(
        self,
        agent_id: UUID,
        collection_id: UUID,
        priority: int = 0
    ) -> Dict[str, Any]:
        """
        Assign a collection to an agent.

        Args:
            agent_id: Agent UUID.
            collection_id: Collection UUID.
            priority: Priority for retrieval ordering.

        Returns:
            Agent-collection assignment record.
        """
        client = await self._get_client()

        payload = {
            "agent_id": str(agent_id),
            "collection_id": str(collection_id),
            "priority": priority
        }

        response = await client.post("/agent-collections", json=payload)
        response.raise_for_status()
        return response.json()

    async def remove_collection_from_agent(
        self,
        agent_id: UUID,
        collection_id: UUID
    ) -> bool:
        """
        Remove a collection assignment from an agent.

        Args:
            agent_id: Agent UUID.
            collection_id: Collection UUID.

        Returns:
            True if removed successfully.
        """
        client = await self._get_client()
        response = await client.delete(f"/agent-collections/{agent_id}/{collection_id}")
        response.raise_for_status()
        return True

    async def get_agent_collections(self, agent_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all collections assigned to an agent.

        Args:
            agent_id: Agent UUID.

        Returns:
            List of collection records with priorities.
        """
        client = await self._get_client()
        response = await client.get(f"/agents/{agent_id}/collections")
        response.raise_for_status()
        return response.json()


# Singleton instance for convenience
_rag_client: Optional[RAGClient] = None


def get_rag_client() -> RAGClient:
    """Get the singleton RAG client instance."""
    global _rag_client
    if _rag_client is None:
        _rag_client = RAGClient()
    return _rag_client


async def close_rag_client():
    """Close the singleton RAG client."""
    global _rag_client
    if _rag_client:
        await _rag_client.close()
        _rag_client = None

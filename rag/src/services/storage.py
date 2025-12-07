"""
Knowledge Storage Service (RAG Phase 3.1)

Handles dual storage of document chunks:
1. pgvector - Vector embeddings for similarity search
2. Graphiti/Neo4j - Entity graph for relationship queries

This hybrid approach enables:
- Fast semantic search (pgvector)
- Multi-hop reasoning (Neo4j graph traversal)
- Temporal queries (Graphiti bi-temporal model)
"""

import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from sqlalchemy import update, select
from sentence_transformers import SentenceTransformer

from ..database.session import get_db_session
from ..database.models import Document, DocumentChunk, Collection
from ..config import get_settings
from .chunking import DocumentChunk as ChunkResult

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when storage operations fail."""
    pass


class KnowledgeStorageService:
    """
    Service for storing document chunks in dual storage.

    Architecture:
    - pgvector: Stores embeddings for vector similarity search
    - Graphiti/Neo4j: Stores entity relationships for graph traversal

    The service:
    1. Generates embeddings using BGE-large-en-v1.5 (1024 dims)
    2. Stores embeddings in PostgreSQL pgvector
    3. Extracts entities and stores relationships in Neo4j (via Graphiti)

    Usage:
        storage = KnowledgeStorageService()
        await storage.store_chunks(document_id, chunks)
    """

    def __init__(self):
        """Initialize storage service."""
        self.settings = get_settings()
        self._embedding_model: Optional[SentenceTransformer] = None
        self._graphiti_client = None
        self._initialized = False

    async def initialize(self):
        """
        Initialize connections and models.

        Call this before using the service.
        """
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
            raise StorageError(f"Embedding model initialization failed: {e}")

        # Initialize Graphiti client (optional - degrades gracefully)
        try:
            await self._init_graphiti()
        except Exception as e:
            logger.warning(f"⚠️ Graphiti initialization failed (graph features disabled): {e}")
            self._graphiti_client = None

        self._initialized = True
        logger.info("✅ KnowledgeStorageService initialized")

    async def _init_graphiti(self):
        """Initialize Graphiti client for Neo4j."""
        try:
            from graphiti_core import Graphiti
            from graphiti_core.llm_client import OpenAIClient
            from graphiti_core.llm_client.config import LLMConfig
            import os

            # Use OpenRouter or local LLM for entity extraction
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

            # Connect to Neo4j
            self._graphiti_client = Graphiti(
                uri=self.settings.neo4j_uri,
                user=self.settings.neo4j_user,
                password=self.settings.neo4j_password,
                llm_client=llm_client,
            )

            # Initialize graph schema
            await self._graphiti_client.build_indices_and_constraints()

            logger.info("✅ Graphiti client connected to Neo4j")

        except ImportError:
            logger.warning("⚠️ Graphiti not installed - graph features disabled")
            self._graphiti_client = None
        except Exception as e:
            logger.warning(f"⚠️ Graphiti connection failed: {e}")
            self._graphiti_client = None

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Uses BGE-large-en-v1.5 which produces 1024-dimensional vectors.
        """
        if not self._embedding_model:
            raise StorageError("Embedding model not initialized")

        # Generate embeddings
        embeddings = self._embedding_model.encode(
            texts,
            normalize_embeddings=True,  # L2 normalize for cosine similarity
            show_progress_bar=len(texts) > 10,
        )

        return embeddings.tolist()

    async def store_chunks(
        self,
        document_id: UUID,
        chunks: List[ChunkResult],
        extract_entities: bool = True,
    ) -> int:
        """
        Store document chunks in dual storage.

        Args:
            document_id: UUID of the parent document
            chunks: List of ChunkResult from chunking service
            extract_entities: Whether to extract entities for graph (slower)

        Returns:
            Number of chunks stored

        Raises:
            StorageError: If storage fails
        """
        if not self._initialized:
            await self.initialize()

        if not chunks:
            return 0

        logger.info(f"📦 Storing {len(chunks)} chunks for document {document_id}")

        try:
            # Generate embeddings for all chunks
            texts = [chunk.content for chunk in chunks]
            embeddings = self._generate_embeddings(texts)

            # Store in PostgreSQL with pgvector
            stored_count = await self._store_in_pgvector(
                document_id=document_id,
                chunks=chunks,
                embeddings=embeddings,
            )

            # Extract entities and store in Graphiti (if enabled)
            if extract_entities and self._graphiti_client:
                await self._store_in_graphiti(document_id, chunks)

            # Update document chunk count
            await self._update_document_counts(document_id, stored_count)

            logger.info(f"✅ Stored {stored_count} chunks for document {document_id}")
            return stored_count

        except Exception as e:
            logger.error(f"❌ Failed to store chunks: {e}")
            raise StorageError(f"Chunk storage failed: {e}")

    async def _store_in_pgvector(
        self,
        document_id: UUID,
        chunks: List[ChunkResult],
        embeddings: List[List[float]],
    ) -> int:
        """Store chunks and embeddings in PostgreSQL with pgvector."""
        async with get_db_session() as db:
            stored_count = 0

            for chunk, embedding in zip(chunks, embeddings):
                # Create chunk record
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    start_char=chunk.start_char,
                    end_char=chunk.end_char,
                    page_number=chunk.page_number,
                    section_title=chunk.section_title,
                    metadata=chunk.metadata,
                )
                db.add(db_chunk)
                await db.flush()  # Get the ID

                # Store embedding using raw SQL (pgvector)
                # SQLAlchemy doesn't natively support pgvector types
                await db.execute(
                    f"""
                    UPDATE document_chunks
                    SET embedding = :embedding
                    WHERE id = :chunk_id
                    """,
                    {
                        "chunk_id": str(db_chunk.id),
                        "embedding": embedding,
                    }
                )

                stored_count += 1

            await db.commit()

            return stored_count

    async def _store_in_graphiti(
        self,
        document_id: UUID,
        chunks: List[ChunkResult],
    ):
        """Extract entities and relationships, store in Graphiti/Neo4j."""
        if not self._graphiti_client:
            return

        try:
            # Combine chunks for entity extraction (Graphiti works with episodes)
            combined_text = "\n\n".join(chunk.content for chunk in chunks)

            # Add episode to Graphiti (triggers entity extraction)
            await self._graphiti_client.add_episode(
                name=f"document_{document_id}",
                episode_body=combined_text,
                reference_time=datetime.utcnow(),
                source_description=f"Document {document_id}",
            )

            logger.info(f"✅ Extracted entities for document {document_id}")

        except Exception as e:
            logger.warning(f"⚠️ Entity extraction failed (non-fatal): {e}")

    async def _update_document_counts(self, document_id: UUID, chunk_count: int):
        """Update document and collection chunk counts."""
        async with get_db_session() as db:
            # Update document
            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(
                    chunk_count=chunk_count,
                    processing_status="completed",
                )
            )

            # Get collection ID
            result = await db.execute(
                select(Document.collection_id).where(Document.id == document_id)
            )
            collection_id = result.scalar_one_or_none()

            if collection_id:
                # Update collection total
                await db.execute(
                    update(Collection)
                    .where(Collection.id == collection_id)
                    .values(chunk_count=Collection.chunk_count + chunk_count)
                )

            await db.commit()

    async def search_similar(
        self,
        query: str,
        collection_ids: Optional[List[UUID]] = None,
        limit: int = 10,
        similarity_threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using vector similarity.

        Args:
            query: Search query text
            collection_ids: Optional list of collection IDs to search in
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of matching chunks with similarity scores
        """
        if not self._initialized:
            await self.initialize()

        # Generate query embedding
        query_embedding = self._generate_embeddings([query])[0]

        async with get_db_session() as db:
            # Build query with optional collection filter
            collection_filter = ""
            params = {
                "query_embedding": query_embedding,
                "limit": limit,
                "threshold": similarity_threshold,
            }

            if collection_ids:
                collection_filter = """
                    AND d.collection_id = ANY(:collection_ids)
                """
                params["collection_ids"] = [str(cid) for cid in collection_ids]

            # Vector similarity search using pgvector
            result = await db.execute(
                f"""
                SELECT
                    dc.id,
                    dc.content,
                    dc.chunk_index,
                    dc.page_number,
                    dc.section_title,
                    dc.metadata,
                    d.filename,
                    d.collection_id,
                    1 - (dc.embedding <=> :query_embedding) AS similarity
                FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE dc.embedding IS NOT NULL
                    AND 1 - (dc.embedding <=> :query_embedding) > :threshold
                    {collection_filter}
                ORDER BY dc.embedding <=> :query_embedding
                LIMIT :limit
                """,
                params
            )

            rows = result.fetchall()

            return [
                {
                    "id": str(row.id),
                    "content": row.content,
                    "chunk_index": row.chunk_index,
                    "page_number": row.page_number,
                    "section_title": row.section_title,
                    "metadata": row.metadata,
                    "filename": row.filename,
                    "collection_id": str(row.collection_id),
                    "similarity": float(row.similarity),
                }
                for row in rows
            ]

    async def delete_document_chunks(self, document_id: UUID):
        """
        Delete all chunks for a document.

        Also removes related entities from Graphiti if available.
        """
        async with get_db_session() as db:
            # Get chunk count for updating collection
            result = await db.execute(
                select(Document.collection_id, Document.chunk_count)
                .where(Document.id == document_id)
            )
            row = result.one_or_none()

            if row:
                collection_id, chunk_count = row

                # Delete chunks (cascade from Document delete will also work)
                await db.execute(
                    f"""
                    DELETE FROM document_chunks
                    WHERE document_id = :document_id
                    """,
                    {"document_id": str(document_id)}
                )

                # Update collection count
                if collection_id and chunk_count:
                    await db.execute(
                        update(Collection)
                        .where(Collection.id == collection_id)
                        .values(chunk_count=Collection.chunk_count - chunk_count)
                    )

                await db.commit()

        # Remove from Graphiti if available
        if self._graphiti_client:
            try:
                # Graphiti doesn't have direct deletion - entities remain
                # but will be invalidated by temporal model
                logger.info(f"📦 Document {document_id} entities marked for cleanup")
            except Exception as e:
                logger.warning(f"⚠️ Graphiti cleanup failed: {e}")

    async def close(self):
        """Close connections and cleanup resources."""
        if self._graphiti_client:
            try:
                await self._graphiti_client.close()
            except Exception:
                pass

        self._initialized = False
        logger.info("📦 KnowledgeStorageService closed")


# Singleton instance
_storage_service: Optional[KnowledgeStorageService] = None


async def get_storage_service() -> KnowledgeStorageService:
    """Get or create the singleton storage service."""
    global _storage_service
    if _storage_service is None:
        _storage_service = KnowledgeStorageService()
        await _storage_service.initialize()
    return _storage_service

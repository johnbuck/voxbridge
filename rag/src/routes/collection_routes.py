"""
Collection API Routes (RAG Phase 3.1)

FastAPI routes for managing knowledge collections and documents.
Collections organize documents for per-agent RAG retrieval.
"""

import hashlib
import os
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query, UploadFile, File, Form, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update

from ..database.session import get_db_session
from ..database.models import Collection, Document, DocumentChunk, AgentCollection, User, Agent
from ..services.processor import process_document_task, process_web_page_task

# ============================================================================
# Request/Response Models
# ============================================================================


class CollectionCreateRequest(BaseModel):
    """Request body for creating a collection"""

    name: str = Field(..., min_length=1, max_length=255, description="Collection name")
    description: Optional[str] = Field(None, max_length=2000, description="Collection description")
    is_public: bool = Field(False, description="Share collection across all agents")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CollectionUpdateRequest(BaseModel):
    """Request body for updating a collection"""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    is_public: Optional[bool] = None
    metadata: Optional[dict] = None


class CollectionResponse(BaseModel):
    """Response model for collection data"""

    id: str
    name: str
    description: Optional[str]
    user_id: str
    is_public: bool
    document_count: int
    chunk_count: int
    metadata: dict
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """Response model for document data"""

    id: str
    collection_id: str
    filename: str
    source_type: str
    source_url: Optional[str]
    mime_type: Optional[str]
    file_size_bytes: Optional[int]
    content_hash: Optional[str]
    chunk_count: int
    processing_status: str
    processing_error: Optional[str]
    metadata: dict
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class DocumentChunkResponse(BaseModel):
    """Response model for document chunk data"""

    id: str
    document_id: str
    chunk_index: int
    content: str
    token_count: Optional[int]
    start_char: Optional[int]
    end_char: Optional[int]
    page_number: Optional[int]
    section_title: Optional[str]
    metadata: dict
    ingested_at: str
    valid_from: str
    valid_until: Optional[str]

    class Config:
        from_attributes = True


class AgentCollectionRequest(BaseModel):
    """Request body for linking agent to collection"""

    agent_id: str = Field(..., description="Agent UUID")
    priority: int = Field(0, ge=0, le=100, description="Collection priority (higher = more relevant)")


class AgentCollectionResponse(BaseModel):
    """Response model for agent-collection link"""

    id: str
    agent_id: str
    collection_id: str
    priority: int
    created_at: str

    class Config:
        from_attributes = True


class WebScrapeRequest(BaseModel):
    """Request body for web scraping"""

    url: str = Field(..., description="URL to scrape")
    title: Optional[str] = Field(None, max_length=500, description="Override document title")


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/api/collections", tags=["collections"])


# ============================================================================
# Collection CRUD Routes
# ============================================================================


@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Collection",
    description="Create a new knowledge collection for organizing documents"
)
async def create_collection(
    request: CollectionCreateRequest,
    user_id: str = Query(..., description="User UUID who owns the collection")
):
    """
    Create a new collection.

    Collections organize documents into logical groups that can be
    assigned to specific agents for RAG retrieval.
    """
    try:
        async with get_db_session() as db:
            # Verify user exists
            user_result = await db.execute(
                select(User).where(User.id == UUID(user_id))
            )
            user = user_result.scalar_one_or_none()
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with ID {user_id} not found"
                )

            # Check for duplicate name
            existing = await db.execute(
                select(Collection).where(
                    Collection.user_id == UUID(user_id),
                    Collection.name == request.name
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Collection with name '{request.name}' already exists for this user"
                )

            # Create collection
            collection = Collection(
                name=request.name,
                description=request.description,
                user_id=UUID(user_id),
                is_public=request.is_public,
                metadata=request.metadata or {},
            )
            db.add(collection)
            await db.commit()
            await db.refresh(collection)

            return CollectionResponse(
                id=str(collection.id),
                name=collection.name,
                description=collection.description,
                user_id=str(collection.user_id),
                is_public=collection.is_public,
                document_count=collection.document_count,
                chunk_count=collection.chunk_count,
                metadata=collection.metadata or {},
                created_at=collection.created_at.isoformat(),
                updated_at=collection.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create collection: {str(e)}"
        )


@router.get(
    "",
    response_model=List[CollectionResponse],
    summary="List Collections",
    description="Get all collections for a user (includes public collections)"
)
async def list_collections(
    user_id: str = Query(..., description="User UUID to filter collections")
):
    """
    Get all collections accessible to a user.

    Returns user's own collections plus any public collections.
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Collection).where(
                    (Collection.user_id == UUID(user_id)) |
                    (Collection.is_public == True)
                ).order_by(Collection.created_at.desc())
            )
            collections = result.scalars().all()

            return [
                CollectionResponse(
                    id=str(c.id),
                    name=c.name,
                    description=c.description,
                    user_id=str(c.user_id),
                    is_public=c.is_public,
                    document_count=c.document_count,
                    chunk_count=c.chunk_count,
                    metadata=c.metadata or {},
                    created_at=c.created_at.isoformat(),
                    updated_at=c.updated_at.isoformat(),
                )
                for c in collections
            ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch collections: {str(e)}"
        )


@router.get(
    "/{collection_id}",
    response_model=CollectionResponse,
    summary="Get Collection",
    description="Get a specific collection by ID"
)
async def get_collection(collection_id: UUID):
    """Get collection by ID."""
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Collection).where(Collection.id == collection_id)
            )
            collection = result.scalar_one_or_none()

            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Collection with ID {collection_id} not found"
                )

            return CollectionResponse(
                id=str(collection.id),
                name=collection.name,
                description=collection.description,
                user_id=str(collection.user_id),
                is_public=collection.is_public,
                document_count=collection.document_count,
                chunk_count=collection.chunk_count,
                metadata=collection.metadata or {},
                created_at=collection.created_at.isoformat(),
                updated_at=collection.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch collection: {str(e)}"
        )


@router.put(
    "/{collection_id}",
    response_model=CollectionResponse,
    summary="Update Collection",
    description="Update a collection's metadata"
)
async def update_collection(collection_id: UUID, request: CollectionUpdateRequest):
    """Update collection metadata."""
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Collection).where(Collection.id == collection_id)
            )
            collection = result.scalar_one_or_none()

            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Collection with ID {collection_id} not found"
                )

            # Update fields
            if request.name is not None:
                collection.name = request.name
            if request.description is not None:
                collection.description = request.description
            if request.is_public is not None:
                collection.is_public = request.is_public
            if request.metadata is not None:
                collection.metadata = request.metadata

            await db.commit()
            await db.refresh(collection)

            return CollectionResponse(
                id=str(collection.id),
                name=collection.name,
                description=collection.description,
                user_id=str(collection.user_id),
                is_public=collection.is_public,
                document_count=collection.document_count,
                chunk_count=collection.chunk_count,
                metadata=collection.metadata or {},
                created_at=collection.created_at.isoformat(),
                updated_at=collection.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update collection: {str(e)}"
        )


@router.delete(
    "/{collection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Collection",
    description="Delete a collection and all its documents"
)
async def delete_collection(collection_id: UUID):
    """
    Delete collection.

    WARNING: This will delete all documents and chunks in the collection.
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Collection).where(Collection.id == collection_id)
            )
            collection = result.scalar_one_or_none()

            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Collection with ID {collection_id} not found"
                )

            await db.delete(collection)
            await db.commit()

            return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete collection: {str(e)}"
        )


# ============================================================================
# Document Upload Routes
# ============================================================================


# Supported file types and their MIME types
SUPPORTED_TYPES = {
    ".pdf": ("pdf", "application/pdf"),
    ".docx": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".doc": ("docx", "application/msword"),
    ".txt": ("txt", "text/plain"),
    ".md": ("md", "text/markdown"),
    ".py": ("code", "text/x-python"),
    ".js": ("code", "text/javascript"),
    ".ts": ("code", "text/typescript"),
    ".java": ("code", "text/x-java"),
    ".cpp": ("code", "text/x-c++"),
    ".c": ("code", "text/x-c"),
    ".go": ("code", "text/x-go"),
    ".rs": ("code", "text/x-rust"),
    ".json": ("code", "application/json"),
    ".yaml": ("code", "text/yaml"),
    ".yml": ("code", "text/yaml"),
}

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post(
    "/{collection_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Document",
    description="Upload a document (PDF, DOCX, TXT, MD, code) to a collection"
)
async def upload_document(
    collection_id: UUID,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None, description="JSON metadata string"),
):
    """
    Upload a document to a collection.

    The document will be queued for processing:
    1. Parse content (PDF, DOCX, TXT, etc.)
    2. Split into chunks (512 tokens, 10% overlap)
    3. Generate embeddings
    4. Store in pgvector

    Supported formats: PDF, DOCX, TXT, MD, and common code files.
    """
    try:
        # Validate file extension
        filename = file.filename or "unknown"
        ext = os.path.splitext(filename.lower())[1]

        if ext not in SUPPORTED_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {ext}. Supported: {', '.join(SUPPORTED_TYPES.keys())}"
            )

        source_type, mime_type = SUPPORTED_TYPES[ext]

        # Read file content
        content = await file.read()
        file_size = len(content)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )

        # Calculate content hash for deduplication
        content_hash = hashlib.sha256(content).hexdigest()

        async with get_db_session() as db:
            # Verify collection exists
            collection_result = await db.execute(
                select(Collection).where(Collection.id == collection_id)
            )
            collection = collection_result.scalar_one_or_none()
            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Collection with ID {collection_id} not found"
                )

            # Check for duplicate content
            existing_result = await db.execute(
                select(Document).where(
                    Document.collection_id == collection_id,
                    Document.content_hash == content_hash
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Document with same content already exists: {existing.filename}"
                )

            # Parse metadata JSON
            doc_metadata = {}
            if metadata:
                import json
                try:
                    doc_metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid metadata JSON"
                    )

            # Create document record
            document = Document(
                collection_id=collection_id,
                filename=filename,
                source_type=source_type,
                mime_type=mime_type,
                file_size_bytes=file_size,
                content_hash=content_hash,
                processing_status="pending",
                metadata=doc_metadata,
            )
            db.add(document)

            # Update collection document count
            await db.execute(
                update(Collection)
                .where(Collection.id == collection_id)
                .values(document_count=Collection.document_count + 1)
            )

            await db.commit()
            await db.refresh(document)

            # Queue background processing
            background_tasks.add_task(process_document_task, document.id, content)

            return DocumentResponse(
                id=str(document.id),
                collection_id=str(document.collection_id),
                filename=document.filename,
                source_type=document.source_type,
                source_url=document.source_url,
                mime_type=document.mime_type,
                file_size_bytes=document.file_size_bytes,
                content_hash=document.content_hash,
                chunk_count=document.chunk_count,
                processing_status=document.processing_status,
                processing_error=document.processing_error,
                metadata=document.metadata or {},
                created_at=document.created_at.isoformat(),
                updated_at=document.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}"
        )


@router.post(
    "/{collection_id}/documents/web",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Scrape Web Page",
    description="Add a web page to the collection by URL"
)
async def scrape_web_page(
    collection_id: UUID,
    request: WebScrapeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Scrape a web page and add it to the collection.

    Uses trafilatura for clean text extraction.
    The page will be queued for processing similar to uploaded documents.
    """
    try:
        async with get_db_session() as db:
            # Verify collection exists
            collection_result = await db.execute(
                select(Collection).where(Collection.id == collection_id)
            )
            collection = collection_result.scalar_one_or_none()
            if not collection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Collection with ID {collection_id} not found"
                )

            # Check for duplicate URL
            existing_result = await db.execute(
                select(Document).where(
                    Document.collection_id == collection_id,
                    Document.source_url == request.url
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"URL already scraped: {existing.filename}"
                )

            # Create document record
            filename = request.title or request.url[:100]
            document = Document(
                collection_id=collection_id,
                filename=filename,
                source_type="web",
                source_url=request.url,
                mime_type="text/html",
                processing_status="pending",
                metadata={"original_url": request.url},
            )
            db.add(document)

            # Update collection document count
            await db.execute(
                update(Collection)
                .where(Collection.id == collection_id)
                .values(document_count=Collection.document_count + 1)
            )

            await db.commit()
            await db.refresh(document)

            # Queue background processing
            background_tasks.add_task(process_web_page_task, document.id, request.url)

            return DocumentResponse(
                id=str(document.id),
                collection_id=str(document.collection_id),
                filename=document.filename,
                source_type=document.source_type,
                source_url=document.source_url,
                mime_type=document.mime_type,
                file_size_bytes=document.file_size_bytes,
                content_hash=document.content_hash,
                chunk_count=document.chunk_count,
                processing_status=document.processing_status,
                processing_error=document.processing_error,
                metadata=document.metadata or {},
                created_at=document.created_at.isoformat(),
                updated_at=document.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to queue web scrape: {str(e)}"
        )


@router.get(
    "/{collection_id}/documents",
    response_model=List[DocumentResponse],
    summary="List Documents",
    description="Get all documents in a collection"
)
async def list_documents(collection_id: UUID):
    """Get all documents in a collection."""
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Document)
                .where(Document.collection_id == collection_id)
                .order_by(Document.created_at.desc())
            )
            documents = result.scalars().all()

            return [
                DocumentResponse(
                    id=str(d.id),
                    collection_id=str(d.collection_id),
                    filename=d.filename,
                    source_type=d.source_type,
                    source_url=d.source_url,
                    mime_type=d.mime_type,
                    file_size_bytes=d.file_size_bytes,
                    content_hash=d.content_hash,
                    chunk_count=d.chunk_count,
                    processing_status=d.processing_status,
                    processing_error=d.processing_error,
                    metadata=d.metadata or {},
                    created_at=d.created_at.isoformat(),
                    updated_at=d.updated_at.isoformat(),
                )
                for d in documents
            ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch documents: {str(e)}"
        )


@router.get(
    "/{collection_id}/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get Document",
    description="Get a specific document by ID"
)
async def get_document(collection_id: UUID, document_id: UUID):
    """Get document by ID."""
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.collection_id == collection_id
                )
            )
            document = result.scalar_one_or_none()

            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document with ID {document_id} not found in collection"
                )

            return DocumentResponse(
                id=str(document.id),
                collection_id=str(document.collection_id),
                filename=document.filename,
                source_type=document.source_type,
                source_url=document.source_url,
                mime_type=document.mime_type,
                file_size_bytes=document.file_size_bytes,
                content_hash=document.content_hash,
                chunk_count=document.chunk_count,
                processing_status=document.processing_status,
                processing_error=document.processing_error,
                metadata=document.metadata or {},
                created_at=document.created_at.isoformat(),
                updated_at=document.updated_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch document: {str(e)}"
        )


@router.delete(
    "/{collection_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
    description="Delete a document and all its chunks"
)
async def delete_document(collection_id: UUID, document_id: UUID):
    """
    Delete document.

    This will also delete all chunks and embeddings associated with the document.
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.collection_id == collection_id
                )
            )
            document = result.scalar_one_or_none()

            if not document:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document with ID {document_id} not found in collection"
                )

            chunk_count = document.chunk_count

            # Delete document (cascades to chunks)
            await db.delete(document)

            # Update collection counts
            await db.execute(
                update(Collection)
                .where(Collection.id == collection_id)
                .values(
                    document_count=Collection.document_count - 1,
                    chunk_count=Collection.chunk_count - chunk_count
                )
            )

            await db.commit()

            return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )


# ============================================================================
# Document Chunks Routes
# ============================================================================


@router.get(
    "/{collection_id}/documents/{document_id}/chunks",
    response_model=List[DocumentChunkResponse],
    summary="List Document Chunks",
    description="Get all chunks for a document"
)
async def list_document_chunks(
    collection_id: UUID,
    document_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get chunks for a document with pagination."""
    try:
        async with get_db_session() as db:
            # Verify document exists in collection
            doc_result = await db.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.collection_id == collection_id
                )
            )
            if not doc_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Document with ID {document_id} not found in collection"
                )

            result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index)
                .limit(limit)
                .offset(offset)
            )
            chunks = result.scalars().all()

            return [
                DocumentChunkResponse(
                    id=str(c.id),
                    document_id=str(c.document_id),
                    chunk_index=c.chunk_index,
                    content=c.content,
                    token_count=c.token_count,
                    start_char=c.start_char,
                    end_char=c.end_char,
                    page_number=c.page_number,
                    section_title=c.section_title,
                    metadata=c.metadata or {},
                    ingested_at=c.ingested_at.isoformat(),
                    valid_from=c.valid_from.isoformat(),
                    valid_until=c.valid_until.isoformat() if c.valid_until else None,
                )
                for c in chunks
            ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch chunks: {str(e)}"
        )


# ============================================================================
# Agent-Collection Binding Routes
# ============================================================================


@router.post(
    "/{collection_id}/agents",
    response_model=AgentCollectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Link Agent to Collection",
    description="Give an agent access to a collection"
)
async def link_agent_to_collection(
    collection_id: UUID,
    request: AgentCollectionRequest,
):
    """
    Link an agent to a collection.

    This enables the agent to use documents from this collection
    during RAG retrieval.
    """
    try:
        async with get_db_session() as db:
            # Verify collection exists
            collection_result = await db.execute(
                select(Collection).where(Collection.id == collection_id)
            )
            if not collection_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Collection with ID {collection_id} not found"
                )

            # Verify agent exists
            agent_result = await db.execute(
                select(Agent).where(Agent.id == UUID(request.agent_id))
            )
            if not agent_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Agent with ID {request.agent_id} not found"
                )

            # Check for existing link
            existing_result = await db.execute(
                select(AgentCollection).where(
                    AgentCollection.agent_id == UUID(request.agent_id),
                    AgentCollection.collection_id == collection_id
                )
            )
            if existing_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Agent already linked to this collection"
                )

            # Create link
            link = AgentCollection(
                agent_id=UUID(request.agent_id),
                collection_id=collection_id,
                priority=request.priority,
            )
            db.add(link)
            await db.commit()
            await db.refresh(link)

            return AgentCollectionResponse(
                id=str(link.id),
                agent_id=str(link.agent_id),
                collection_id=str(link.collection_id),
                priority=link.priority,
                created_at=link.created_at.isoformat(),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to link agent: {str(e)}"
        )


@router.get(
    "/{collection_id}/agents",
    response_model=List[AgentCollectionResponse],
    summary="List Linked Agents",
    description="Get all agents linked to a collection"
)
async def list_linked_agents(collection_id: UUID):
    """Get all agents linked to a collection."""
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(AgentCollection)
                .where(AgentCollection.collection_id == collection_id)
                .order_by(AgentCollection.priority.desc())
            )
            links = result.scalars().all()

            return [
                AgentCollectionResponse(
                    id=str(link.id),
                    agent_id=str(link.agent_id),
                    collection_id=str(link.collection_id),
                    priority=link.priority,
                    created_at=link.created_at.isoformat(),
                )
                for link in links
            ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch linked agents: {str(e)}"
        )


@router.delete(
    "/{collection_id}/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unlink Agent from Collection",
    description="Remove agent's access to a collection"
)
async def unlink_agent_from_collection(collection_id: UUID, agent_id: UUID):
    """
    Unlink an agent from a collection.

    The agent will no longer have access to documents from this collection.
    """
    try:
        async with get_db_session() as db:
            result = await db.execute(
                select(AgentCollection).where(
                    AgentCollection.agent_id == agent_id,
                    AgentCollection.collection_id == collection_id
                )
            )
            link = result.scalar_one_or_none()

            if not link:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Agent-collection link not found"
                )

            await db.delete(link)
            await db.commit()

            return None
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to unlink agent: {str(e)}"
        )

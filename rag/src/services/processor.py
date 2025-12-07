"""
Document Processing Worker (RAG Phase 3.1)

Orchestrates the document ingestion pipeline:
1. Parse document (unstructured.io)
2. Chunk content (RecursiveCharacterTextSplitter)
3. Generate embeddings & store (pgvector + Graphiti)

This worker runs asynchronously to avoid blocking the API.
"""

import logging
import asyncio
from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import update

from ..database.session import get_db_session
from ..database.models import Document
from .ingestion import DocumentIngestionService, get_ingestion_service, DocumentParseError
from .web_scraper import WebScraperService, get_scraper_service, WebScrapeError
from .chunking import ChunkingService, get_chunking_service
from .storage import KnowledgeStorageService, get_storage_service, StorageError

logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    """Raised when document processing fails."""
    pass


class DocumentProcessor:
    """
    Orchestrates document processing pipeline.

    Pipeline stages:
    1. Ingestion: Parse document format (PDF, DOCX, etc.)
    2. Chunking: Split into 512-token chunks with 10% overlap
    3. Storage: Generate embeddings and store in dual storage

    Usage:
        processor = DocumentProcessor()
        await processor.process_document(document_id, file_content)
    """

    def __init__(self):
        """Initialize processor with services."""
        self.ingestion_service: Optional[DocumentIngestionService] = None
        self.scraper_service: Optional[WebScraperService] = None
        self.chunking_service: Optional[ChunkingService] = None
        self.storage_service: Optional[KnowledgeStorageService] = None
        self._initialized = False

    async def initialize(self):
        """Initialize all services."""
        if self._initialized:
            return

        self.ingestion_service = get_ingestion_service()
        self.scraper_service = get_scraper_service()
        self.chunking_service = get_chunking_service()
        self.storage_service = await get_storage_service()

        self._initialized = True
        logger.info("✅ DocumentProcessor initialized")

    async def process_document(
        self,
        document_id: UUID,
        content: bytes,
        extract_entities: bool = True,
    ) -> int:
        """
        Process a document through the full pipeline.

        Args:
            document_id: UUID of the document record
            content: Raw file content as bytes
            extract_entities: Whether to extract entities for graph

        Returns:
            Number of chunks created

        Raises:
            DocumentProcessingError: If processing fails
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()
        logger.info(f"📄 Starting document processing: {document_id}")

        try:
            # Update status to processing
            await self._update_status(document_id, "processing")

            # Get document info
            async with get_db_session() as db:
                from sqlalchemy import select
                result = await db.execute(
                    select(Document).where(Document.id == document_id)
                )
                document = result.scalar_one_or_none()

            if not document:
                raise DocumentProcessingError(f"Document {document_id} not found")

            # Stage 1: Ingest document
            logger.info(f"📄 Stage 1: Ingesting {document.filename}")
            ingested = await self.ingestion_service.ingest_file(
                content=content,
                filename=document.filename,
                source_type=document.source_type,
            )

            # Stage 2: Chunk content
            logger.info(f"📦 Stage 2: Chunking {ingested.char_count} chars")
            chunks = self.chunking_service.chunk_text(
                text=ingested.text,
                metadata={
                    "filename": document.filename,
                    "source_type": document.source_type,
                    "title": ingested.title,
                    "author": ingested.author,
                },
            )

            if ingested.sections:
                # Use section-aware chunking for better context
                chunks = self.chunking_service.chunk_with_sections(
                    text=ingested.text,
                    sections=ingested.sections,
                    metadata={
                        "filename": document.filename,
                        "source_type": document.source_type,
                    },
                )

            # Stage 3: Store with embeddings
            logger.info(f"📦 Stage 3: Storing {len(chunks)} chunks")
            stored_count = await self.storage_service.store_chunks(
                document_id=document_id,
                chunks=chunks,
                extract_entities=extract_entities,
            )

            # Update status to completed
            await self._update_status(document_id, "completed")

            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"✅ Document {document_id} processed: "
                f"{stored_count} chunks in {duration:.2f}s"
            )

            return stored_count

        except (DocumentParseError, StorageError) as e:
            await self._update_status(document_id, "failed", str(e))
            raise DocumentProcessingError(str(e))
        except Exception as e:
            await self._update_status(document_id, "failed", str(e))
            logger.error(f"❌ Document processing failed: {e}")
            raise DocumentProcessingError(f"Processing failed: {e}")

    async def process_web_page(
        self,
        document_id: UUID,
        url: str,
        extract_entities: bool = True,
    ) -> int:
        """
        Process a web page through the pipeline.

        Args:
            document_id: UUID of the document record
            url: URL to scrape
            extract_entities: Whether to extract entities for graph

        Returns:
            Number of chunks created
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()
        logger.info(f"🌐 Starting web page processing: {url}")

        try:
            # Update status to processing
            await self._update_status(document_id, "processing")

            # Stage 1: Scrape web page
            logger.info(f"🌐 Stage 1: Scraping {url}")
            scraped = await self.scraper_service.scrape_url(url)

            # Update document with scraped info
            async with get_db_session() as db:
                await db.execute(
                    update(Document)
                    .where(Document.id == document_id)
                    .values(
                        filename=scraped.title or url[:100],
                        content_hash=scraped.content_hash,
                        file_size_bytes=scraped.char_count,
                        metadata={
                            "title": scraped.title,
                            "author": scraped.author,
                            "date": scraped.date,
                            "description": scraped.description,
                            "scraped_at": scraped.scraped_at,
                        },
                    )
                )
                await db.commit()

            # Stage 2: Chunk content
            logger.info(f"📦 Stage 2: Chunking {scraped.char_count} chars")
            chunks = self.chunking_service.chunk_text(
                text=scraped.text,
                metadata={
                    "url": url,
                    "title": scraped.title,
                    "author": scraped.author,
                    "source_type": "web",
                },
            )

            # Stage 3: Store with embeddings
            logger.info(f"📦 Stage 3: Storing {len(chunks)} chunks")
            stored_count = await self.storage_service.store_chunks(
                document_id=document_id,
                chunks=chunks,
                extract_entities=extract_entities,
            )

            # Update status to completed
            await self._update_status(document_id, "completed")

            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.info(
                f"✅ Web page processed: {stored_count} chunks in {duration:.2f}s"
            )

            return stored_count

        except WebScrapeError as e:
            await self._update_status(document_id, "failed", str(e))
            raise DocumentProcessingError(str(e))
        except Exception as e:
            await self._update_status(document_id, "failed", str(e))
            logger.error(f"❌ Web page processing failed: {e}")
            raise DocumentProcessingError(f"Processing failed: {e}")

    async def _update_status(
        self,
        document_id: UUID,
        status: str,
        error: Optional[str] = None,
    ):
        """Update document processing status."""
        async with get_db_session() as db:
            values = {"processing_status": status}
            if error:
                values["processing_error"] = error[:1000]  # Truncate long errors

            await db.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(**values)
            )
            await db.commit()

    async def reprocess_failed(self) -> int:
        """
        Reprocess all failed documents.

        Returns:
            Number of documents reprocessed
        """
        async with get_db_session() as db:
            from sqlalchemy import select
            result = await db.execute(
                select(Document).where(Document.processing_status == "failed")
            )
            failed_docs = result.scalars().all()

        if not failed_docs:
            logger.info("📦 No failed documents to reprocess")
            return 0

        logger.info(f"📦 Reprocessing {len(failed_docs)} failed documents")
        reprocessed = 0

        for doc in failed_docs:
            try:
                if doc.source_type == "web" and doc.source_url:
                    await self.process_web_page(doc.id, doc.source_url)
                else:
                    # Would need to re-fetch content for file uploads
                    logger.warning(f"⚠️ Cannot reprocess file {doc.id} - content not stored")
                    continue

                reprocessed += 1
            except DocumentProcessingError as e:
                logger.error(f"❌ Reprocessing failed for {doc.id}: {e}")

        return reprocessed


# Singleton instance
_processor: Optional[DocumentProcessor] = None


async def get_processor() -> DocumentProcessor:
    """Get or create the singleton processor."""
    global _processor
    if _processor is None:
        _processor = DocumentProcessor()
        await _processor.initialize()
    return _processor


# Background task functions for FastAPI BackgroundTasks


async def process_document_task(document_id: UUID, content: bytes):
    """Background task for processing uploaded documents."""
    try:
        processor = await get_processor()
        await processor.process_document(document_id, content)
    except Exception as e:
        logger.error(f"❌ Background document processing failed: {e}")


async def process_web_page_task(document_id: UUID, url: str):
    """Background task for processing web pages."""
    try:
        processor = await get_processor()
        await processor.process_web_page(document_id, url)
    except Exception as e:
        logger.error(f"❌ Background web page processing failed: {e}")

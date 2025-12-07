"""
Document Ingestion Service (RAG Phase 3.1)

Parses documents using unstructured.io for PDF, DOCX, TXT, MD, and code files.
Extracts text content, metadata, and structural information.
"""

import logging
import tempfile
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class DocumentParseError(Exception):
    """Raised when document parsing fails."""
    pass


@dataclass
class IngestedDocument:
    """
    Result of document ingestion.

    Contains extracted text, metadata, and structural information
    for downstream chunking and embedding.
    """

    # Core content
    text: str
    filename: str
    source_type: str  # 'pdf', 'docx', 'txt', 'md', 'code', 'web'

    # Document metadata
    title: Optional[str] = None
    author: Optional[str] = None
    creation_date: Optional[str] = None
    language: Optional[str] = None

    # Structural information
    page_count: Optional[int] = None
    sections: List[Dict[str, Any]] = field(default_factory=list)

    # Processing info
    char_count: int = 0
    word_count: int = 0

    def __post_init__(self):
        """Calculate counts after initialization."""
        self.char_count = len(self.text)
        self.word_count = len(self.text.split())


class DocumentIngestionService:
    """
    Service for parsing documents using unstructured.io.

    Supports:
    - PDF files (with OCR fallback)
    - DOCX/DOC files
    - TXT files
    - Markdown files
    - Code files (Python, JavaScript, etc.)

    Usage:
        service = DocumentIngestionService()
        result = await service.ingest_file(file_bytes, "document.pdf")
        print(result.text)
    """

    def __init__(self):
        """Initialize ingestion service."""
        self._initialized = False
        self._unstructured_available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if unstructured is available."""
        try:
            from unstructured.partition.auto import partition
            self._unstructured_available = True
            self._initialized = True
            logger.info("📚 DocumentIngestionService initialized with unstructured.io")
        except ImportError as e:
            logger.warning(f"⚠️ unstructured.io not available: {e}")
            logger.warning("⚠️ Falling back to basic text extraction")
            self._unstructured_available = False
            self._initialized = True

    async def ingest_file(
        self,
        content: bytes,
        filename: str,
        source_type: Optional[str] = None,
    ) -> IngestedDocument:
        """
        Ingest a file and extract its content.

        Args:
            content: File content as bytes
            filename: Original filename
            source_type: Override source type (auto-detected if not provided)

        Returns:
            IngestedDocument with extracted content and metadata

        Raises:
            DocumentParseError: If parsing fails
        """
        if not source_type:
            source_type = self._detect_source_type(filename)

        logger.info(f"📄 Ingesting {filename} (type: {source_type})")

        try:
            if self._unstructured_available:
                return await self._ingest_with_unstructured(content, filename, source_type)
            else:
                return await self._ingest_basic(content, filename, source_type)
        except Exception as e:
            logger.error(f"❌ Failed to ingest {filename}: {e}")
            raise DocumentParseError(f"Failed to parse {filename}: {str(e)}")

    def _detect_source_type(self, filename: str) -> str:
        """Detect source type from filename extension."""
        ext = Path(filename).suffix.lower()

        type_map = {
            ".pdf": "pdf",
            ".docx": "docx",
            ".doc": "docx",
            ".txt": "txt",
            ".md": "md",
            ".markdown": "md",
            ".py": "code",
            ".js": "code",
            ".ts": "code",
            ".java": "code",
            ".cpp": "code",
            ".c": "code",
            ".go": "code",
            ".rs": "code",
            ".json": "code",
            ".yaml": "code",
            ".yml": "code",
            ".html": "web",
            ".htm": "web",
        }

        return type_map.get(ext, "txt")

    async def _ingest_with_unstructured(
        self,
        content: bytes,
        filename: str,
        source_type: str,
    ) -> IngestedDocument:
        """
        Ingest document using unstructured.io.

        Uses the partition() function for automatic format detection
        and extraction.
        """
        from unstructured.partition.auto import partition

        # Write to temp file for unstructured
        with tempfile.NamedTemporaryFile(
            suffix=Path(filename).suffix,
            delete=False
        ) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            # Partition document into elements
            elements = partition(filename=tmp_path)

            # Extract text from elements
            text_parts = []
            sections = []
            current_section = None
            page_count = 0

            for element in elements:
                element_type = type(element).__name__
                element_text = str(element)

                # Track page numbers if available
                if hasattr(element, 'metadata') and hasattr(element.metadata, 'page_number'):
                    page_num = element.metadata.page_number
                    if page_num and page_num > page_count:
                        page_count = page_num

                # Track sections (headers become section markers)
                if element_type in ('Title', 'Header'):
                    if current_section:
                        sections.append(current_section)
                    current_section = {
                        'title': element_text,
                        'start_index': len('\n\n'.join(text_parts)),
                        'elements': [],
                    }

                # Add text
                if element_text.strip():
                    text_parts.append(element_text)
                    if current_section:
                        current_section['elements'].append({
                            'type': element_type,
                            'text': element_text[:200],  # Preview
                        })

            # Add last section
            if current_section:
                sections.append(current_section)

            # Combine text
            full_text = '\n\n'.join(text_parts)

            # Extract metadata
            title = None
            author = None
            creation_date = None

            if elements and hasattr(elements[0], 'metadata'):
                meta = elements[0].metadata
                title = getattr(meta, 'filename', None) or filename
                # Some formats include author/date in metadata
                if hasattr(meta, 'last_modified_by'):
                    author = meta.last_modified_by
                if hasattr(meta, 'created'):
                    creation_date = str(meta.created)

            logger.info(
                f"✅ Ingested {filename}: {len(full_text)} chars, "
                f"{len(sections)} sections, {page_count} pages"
            )

            return IngestedDocument(
                text=full_text,
                filename=filename,
                source_type=source_type,
                title=title or filename,
                author=author,
                creation_date=creation_date,
                page_count=page_count if page_count > 0 else None,
                sections=sections,
            )

        finally:
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    async def _ingest_basic(
        self,
        content: bytes,
        filename: str,
        source_type: str,
    ) -> IngestedDocument:
        """
        Basic text extraction fallback.

        Used when unstructured.io is not available.
        Only handles plain text formats well.
        """
        # Try common encodings
        text = None
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'ascii']:
            try:
                text = content.decode(encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if text is None:
            raise DocumentParseError(f"Could not decode {filename} with any known encoding")

        # For binary formats, warn user
        if source_type in ('pdf', 'docx'):
            logger.warning(
                f"⚠️ {source_type.upper()} parsing requires unstructured.io. "
                f"Only raw text extracted from {filename}"
            )

        logger.info(f"✅ Basic ingestion of {filename}: {len(text)} chars")

        return IngestedDocument(
            text=text,
            filename=filename,
            source_type=source_type,
            title=filename,
        )

    async def ingest_text(
        self,
        text: str,
        filename: str = "text_input",
        source_type: str = "txt",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestedDocument:
        """
        Ingest raw text directly.

        Useful for web-scraped content or API responses.

        Args:
            text: Text content
            filename: Virtual filename for tracking
            source_type: Source type identifier
            metadata: Additional metadata

        Returns:
            IngestedDocument with the text
        """
        metadata = metadata or {}

        return IngestedDocument(
            text=text,
            filename=filename,
            source_type=source_type,
            title=metadata.get('title', filename),
            author=metadata.get('author'),
            creation_date=metadata.get('creation_date'),
        )


# Singleton instance
_ingestion_service: Optional[DocumentIngestionService] = None


def get_ingestion_service() -> DocumentIngestionService:
    """Get or create the singleton ingestion service."""
    global _ingestion_service
    if _ingestion_service is None:
        _ingestion_service = DocumentIngestionService()
    return _ingestion_service

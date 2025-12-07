"""
Chunking Service (RAG Phase 3.1)

Splits documents into chunks for embedding using RecursiveCharacterTextSplitter.
Implements best practices: 512 tokens with 10% overlap.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import tiktoken

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """
    A chunk of a document for embedding.

    Contains the text content along with metadata
    for tracking position and context.
    """

    # Core content
    content: str
    chunk_index: int

    # Position in original document
    start_char: int
    end_char: int

    # Token count (for embedding budgets)
    token_count: int

    # Context (optional)
    page_number: Optional[int] = None
    section_title: Optional[str] = None

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class ChunkingService:
    """
    Service for splitting documents into chunks.

    Uses RecursiveCharacterTextSplitter from langchain-text-splitters
    with configurable chunk size and overlap.

    Best Practices (from RAG research):
    - 512 tokens per chunk (optimal for most embedding models)
    - 10% overlap (prevents context loss at boundaries)
    - Recursive splitting (respects document structure)

    Usage:
        chunker = ChunkingService()
        chunks = chunker.chunk_text("Long document text...")
        for chunk in chunks:
            print(f"Chunk {chunk.chunk_index}: {len(chunk.content)} chars")
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap_percent: Optional[int] = None,
        encoding_name: str = "cl100k_base",
    ):
        """
        Initialize chunking service.

        Args:
            chunk_size: Number of tokens per chunk (default from config)
            chunk_overlap_percent: Overlap as percentage (default from config)
            encoding_name: Tiktoken encoding for token counting
        """
        settings = get_settings()

        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap_percent = chunk_overlap_percent or settings.chunk_overlap
        self.chunk_overlap = int(self.chunk_size * self.chunk_overlap_percent / 100)

        # Initialize tokenizer for token counting
        try:
            self.tokenizer = tiktoken.get_encoding(encoding_name)
        except Exception:
            # Fallback to cl100k_base (GPT-4 encoding)
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

        self._initialized = False
        self._langchain_available = False
        self._check_dependencies()

        logger.info(
            f"📦 ChunkingService initialized: "
            f"chunk_size={self.chunk_size}, overlap={self.chunk_overlap} "
            f"({self.chunk_overlap_percent}%)"
        )

    def _check_dependencies(self):
        """Check if langchain-text-splitters is available."""
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            self._langchain_available = True
            self._initialized = True
        except ImportError as e:
            logger.warning(f"⚠️ langchain-text-splitters not available: {e}")
            logger.warning("⚠️ Falling back to basic chunking")
            self._langchain_available = False
            self._initialized = True

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.tokenizer.encode(text))

    def _estimate_chars_per_token(self, sample_text: str) -> float:
        """Estimate average characters per token for a text sample."""
        if not sample_text:
            return 4.0  # Default estimate

        tokens = self._count_tokens(sample_text)
        if tokens == 0:
            return 4.0

        return len(sample_text) / tokens

    def chunk_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        """
        Split text into chunks.

        Args:
            text: Text content to chunk
            metadata: Optional metadata to attach to chunks

        Returns:
            List of DocumentChunk objects
        """
        if not text or not text.strip():
            return []

        metadata = metadata or {}

        if self._langchain_available:
            return self._chunk_with_langchain(text, metadata)
        else:
            return self._chunk_basic(text, metadata)

    def _chunk_with_langchain(
        self,
        text: str,
        metadata: Dict[str, Any],
    ) -> List[DocumentChunk]:
        """
        Chunk text using RecursiveCharacterTextSplitter.

        The splitter respects document structure by trying to split on:
        1. Paragraphs (\n\n)
        2. Lines (\n)
        3. Sentences (. ! ?)
        4. Words (spaces)
        5. Characters (last resort)
        """
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        # Estimate character count for token-based chunking
        chars_per_token = self._estimate_chars_per_token(text[:1000])
        chunk_size_chars = int(self.chunk_size * chars_per_token)
        overlap_chars = int(self.chunk_overlap * chars_per_token)

        # Create splitter with token-based length function
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size_chars,
            chunk_overlap=overlap_chars,
            length_function=len,  # Use character count for splitting
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
            keep_separator=True,
        )

        # Split text
        splits = splitter.split_text(text)

        # Convert to DocumentChunk objects with position tracking
        chunks = []
        current_pos = 0

        for i, split_text in enumerate(splits):
            # Find actual position in original text
            start_pos = text.find(split_text, current_pos)
            if start_pos == -1:
                # Fallback if exact match not found (due to separator handling)
                start_pos = current_pos

            end_pos = start_pos + len(split_text)

            # Count tokens
            token_count = self._count_tokens(split_text)

            # Extract section title if present (look for headers)
            section_title = self._extract_section_title(split_text)

            # Detect page number from metadata if available
            page_number = metadata.get("page_number")

            chunk = DocumentChunk(
                content=split_text,
                chunk_index=i,
                start_char=start_pos,
                end_char=end_pos,
                token_count=token_count,
                page_number=page_number,
                section_title=section_title,
                metadata={
                    **metadata,
                    "source_length": len(text),
                    "relative_position": start_pos / len(text) if text else 0,
                },
            )
            chunks.append(chunk)

            # Update position for next search (account for overlap)
            current_pos = max(start_pos + 1, end_pos - overlap_chars)

        logger.info(
            f"📦 Chunked {len(text)} chars into {len(chunks)} chunks "
            f"(avg {sum(c.token_count for c in chunks) // max(len(chunks), 1)} tokens/chunk)"
        )

        return chunks

    def _chunk_basic(
        self,
        text: str,
        metadata: Dict[str, Any],
    ) -> List[DocumentChunk]:
        """
        Basic chunking fallback.

        Uses simple paragraph-based splitting when langchain is unavailable.
        """
        # Estimate character count for chunk size
        chars_per_token = self._estimate_chars_per_token(text[:1000])
        chunk_size_chars = int(self.chunk_size * chars_per_token)
        overlap_chars = int(self.chunk_overlap * chars_per_token)

        chunks = []
        current_pos = 0
        chunk_index = 0

        while current_pos < len(text):
            # Calculate end position
            end_pos = min(current_pos + chunk_size_chars, len(text))

            # Try to break at paragraph or sentence boundary
            if end_pos < len(text):
                # Look for paragraph break
                para_break = text.rfind("\n\n", current_pos, end_pos)
                if para_break > current_pos + chunk_size_chars // 2:
                    end_pos = para_break + 2

                # Look for sentence break
                elif (sentence_break := text.rfind(". ", current_pos, end_pos)) > current_pos + chunk_size_chars // 2:
                    end_pos = sentence_break + 2

            # Extract chunk text
            chunk_text = text[current_pos:end_pos].strip()

            if chunk_text:
                token_count = self._count_tokens(chunk_text)
                section_title = self._extract_section_title(chunk_text)

                chunk = DocumentChunk(
                    content=chunk_text,
                    chunk_index=chunk_index,
                    start_char=current_pos,
                    end_char=end_pos,
                    token_count=token_count,
                    section_title=section_title,
                    metadata={
                        **metadata,
                        "source_length": len(text),
                        "relative_position": current_pos / len(text) if text else 0,
                    },
                )
                chunks.append(chunk)
                chunk_index += 1

            # Move to next position with overlap
            current_pos = end_pos - overlap_chars
            if current_pos >= end_pos:
                current_pos = end_pos

        logger.info(
            f"📦 Basic chunked {len(text)} chars into {len(chunks)} chunks"
        )

        return chunks

    def _extract_section_title(self, text: str) -> Optional[str]:
        """
        Extract section title from chunk if present.

        Looks for common header patterns at the start of the chunk.
        """
        import re

        # Check first 200 chars for header patterns
        sample = text[:200]

        # Markdown headers
        md_match = re.match(r'^#{1,6}\s+(.+?)(?:\n|$)', sample)
        if md_match:
            return md_match.group(1).strip()

        # All-caps headers (common in PDFs)
        caps_match = re.match(r'^([A-Z][A-Z\s]{10,50})(?:\n|$)', sample)
        if caps_match:
            return caps_match.group(1).strip()

        # Title case headers followed by newline
        title_match = re.match(r'^([A-Z][a-zA-Z\s]{5,50}):\s*\n', sample)
        if title_match:
            return title_match.group(1).strip()

        return None

    def chunk_with_sections(
        self,
        text: str,
        sections: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[DocumentChunk]:
        """
        Chunk text respecting section boundaries.

        Each section is chunked separately to preserve context.

        Args:
            text: Full document text
            sections: List of section dicts with 'title' and 'start_index'
            metadata: Optional metadata to attach to chunks

        Returns:
            List of DocumentChunk objects with section info
        """
        metadata = metadata or {}
        all_chunks = []
        current_chunk_index = 0

        for i, section in enumerate(sections):
            section_title = section.get("title", "")
            start_idx = section.get("start_index", 0)

            # Determine end of section
            if i + 1 < len(sections):
                end_idx = sections[i + 1].get("start_index", len(text))
            else:
                end_idx = len(text)

            # Extract section text
            section_text = text[start_idx:end_idx]

            if not section_text.strip():
                continue

            # Chunk the section
            section_metadata = {
                **metadata,
                "section_index": i,
                "section_title": section_title,
            }

            section_chunks = self.chunk_text(section_text, section_metadata)

            # Update chunk indices and positions
            for chunk in section_chunks:
                chunk.chunk_index = current_chunk_index
                chunk.start_char += start_idx
                chunk.end_char += start_idx
                chunk.section_title = section_title or chunk.section_title
                current_chunk_index += 1

            all_chunks.extend(section_chunks)

        return all_chunks


# Singleton instance
_chunking_service: Optional[ChunkingService] = None


def get_chunking_service() -> ChunkingService:
    """Get or create the singleton chunking service."""
    global _chunking_service
    if _chunking_service is None:
        _chunking_service = ChunkingService()
    return _chunking_service

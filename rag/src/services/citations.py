"""
Citation Generation Service (RAG Phase 3.1d)

Generates source citations for RAG responses.
Enables transparency by showing which documents contributed to an answer.
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from .retrieval import RetrievalResult

logger = logging.getLogger(__name__)


@dataclass
class Citation:
    """A source citation for an AI response."""

    # Reference info
    index: int  # Citation number [1], [2], etc.
    document_name: str
    collection_name: Optional[str] = None

    # Location info
    page_number: Optional[int] = None
    section_title: Optional[str] = None
    chunk_index: int = 0

    # Relevance
    relevance_score: float = 0.0

    # Content preview
    excerpt: str = ""
    excerpt_max_chars: int = 200

    # IDs for linking
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    collection_id: Optional[str] = None

    def to_markdown(self) -> str:
        """Format citation as markdown."""
        parts = [f"[{self.index}]"]

        if self.document_name:
            parts.append(f"**{self.document_name}**")

        if self.page_number:
            parts.append(f"p.{self.page_number}")
        elif self.section_title:
            parts.append(f"'{self.section_title}'")

        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "index": self.index,
            "document_name": self.document_name,
            "collection_name": self.collection_name,
            "page_number": self.page_number,
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "relevance_score": self.relevance_score,
            "excerpt": self.excerpt,
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "collection_id": self.collection_id,
        }


@dataclass
class CitedResponse:
    """An AI response with citations."""

    content: str
    citations: List[Citation]
    sources_used: int = 0

    def format_with_citations(self) -> str:
        """Format response with inline citation markers."""
        if not self.citations:
            return self.content

        # Response already contains citation markers [1], [2], etc.
        # Add citation list at the end
        citation_list = "\n\n**Sources:**\n"
        for citation in self.citations:
            citation_list += f"- {citation.to_markdown()}\n"

        return self.content + citation_list

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "content": self.content,
            "citations": [c.to_dict() for c in self.citations],
            "sources_used": self.sources_used,
        }


class CitationService:
    """
    Service for generating citations from retrieval results.

    Features:
    - Automatic citation numbering
    - Excerpt generation with highlighting
    - Multiple citation formats (markdown, JSON)
    - Deduplication by document

    Usage:
        citation_service = CitationService()
        citations = citation_service.generate_citations(retrieval_results)
        response = citation_service.create_cited_response(ai_response, citations)
    """

    def __init__(
        self,
        max_citations: int = 5,
        excerpt_max_chars: int = 200,
        min_relevance_score: float = 0.3,
    ):
        """
        Initialize citation service.

        Args:
            max_citations: Maximum number of citations to include
            excerpt_max_chars: Maximum characters in excerpt
            min_relevance_score: Minimum score for citation inclusion
        """
        self.max_citations = max_citations
        self.excerpt_max_chars = excerpt_max_chars
        self.min_relevance_score = min_relevance_score

    def generate_citations(
        self,
        results: List[RetrievalResult],
        query: Optional[str] = None,
    ) -> List[Citation]:
        """
        Generate citations from retrieval results.

        Args:
            results: Retrieval results to cite
            query: Optional query for excerpt highlighting

        Returns:
            List of Citation objects
        """
        citations = []
        seen_documents = set()

        for i, result in enumerate(results):
            # Skip low-relevance results
            if result.score < self.min_relevance_score:
                continue

            # Deduplicate by document
            if result.document_id in seen_documents:
                continue
            seen_documents.add(result.document_id)

            # Generate excerpt
            excerpt = self._generate_excerpt(result.content, query)

            citation = Citation(
                index=len(citations) + 1,
                document_name=result.document_name,
                collection_name=result.collection_name,
                page_number=result.page_number,
                section_title=result.section_title,
                chunk_index=result.chunk_index,
                relevance_score=result.score,
                excerpt=excerpt,
                excerpt_max_chars=self.excerpt_max_chars,
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                collection_id=result.collection_id,
            )
            citations.append(citation)

            if len(citations) >= self.max_citations:
                break

        logger.debug(f"📚 Generated {len(citations)} citations from {len(results)} results")
        return citations

    def _generate_excerpt(
        self,
        content: str,
        query: Optional[str] = None,
    ) -> str:
        """
        Generate a relevant excerpt from content.

        If query is provided, tries to center excerpt around matching terms.
        """
        if len(content) <= self.excerpt_max_chars:
            return content

        # If no query, just take the beginning
        if not query:
            return content[:self.excerpt_max_chars - 3] + "..."

        # Find best matching position
        query_terms = query.lower().split()
        content_lower = content.lower()

        best_pos = 0
        best_score = 0

        # Slide window and count matching terms
        window_size = self.excerpt_max_chars
        for i in range(0, len(content) - window_size, 50):
            window = content_lower[i:i + window_size]
            score = sum(1 for term in query_terms if term in window)
            if score > best_score:
                best_score = score
                best_pos = i

        # Extract excerpt
        excerpt = content[best_pos:best_pos + self.excerpt_max_chars]

        # Clean up boundaries
        if best_pos > 0:
            # Start at word boundary
            space_pos = excerpt.find(' ')
            if space_pos > 0 and space_pos < 20:
                excerpt = "..." + excerpt[space_pos + 1:]

        if best_pos + self.excerpt_max_chars < len(content):
            # End at word boundary
            last_space = excerpt.rfind(' ')
            if last_space > len(excerpt) - 20:
                excerpt = excerpt[:last_space] + "..."
            else:
                excerpt = excerpt + "..."

        return excerpt

    def create_cited_response(
        self,
        response_content: str,
        citations: List[Citation],
    ) -> CitedResponse:
        """
        Create a cited response with automatic citation injection.

        This method can optionally inject citation markers into the response
        if the AI didn't include them.

        Args:
            response_content: AI-generated response
            citations: List of citations to include

        Returns:
            CitedResponse with content and citations
        """
        return CitedResponse(
            content=response_content,
            citations=citations,
            sources_used=len(citations),
        )

    def format_context_for_llm(
        self,
        results: List[RetrievalResult],
        include_citations: bool = True,
    ) -> str:
        """
        Format retrieval results as context for LLM prompt.

        Includes citation markers that the LLM can reference in its response.

        Args:
            results: Retrieval results to format
            include_citations: Whether to include citation markers

        Returns:
            Formatted context string
        """
        if not results:
            return ""

        context_parts = ["Here is relevant context from the knowledge base:\n"]

        for i, result in enumerate(results[:self.max_citations], 1):
            if include_citations:
                header = f"\n[{i}] From '{result.document_name}'"
                if result.section_title:
                    header += f" - {result.section_title}"
                if result.page_number:
                    header += f" (p.{result.page_number})"
                header += ":\n"
            else:
                header = "\n---\n"

            context_parts.append(header)
            context_parts.append(result.content)

        context_parts.append("\n\n---\nUse the information above to answer the question. ")
        if include_citations:
            context_parts.append("Reference sources using [1], [2], etc. when appropriate.")

        return "".join(context_parts)


# Singleton instance
_citation_service: Optional[CitationService] = None


def get_citation_service() -> CitationService:
    """Get or create the singleton citation service."""
    global _citation_service
    if _citation_service is None:
        _citation_service = CitationService()
    return _citation_service

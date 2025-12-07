"""
Entity Extraction Service (RAG Phase 3.1c)

Extracts entities and relationships from document chunks using LLM.
Stores extracted entities in Graphiti/Neo4j for graph-based retrieval.

Entity types:
- Person, Organization, Location, Event
- Concept, Technology, Product
- Date, Time, Duration
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """Extracted entity from text."""

    name: str
    entity_type: str  # Person, Organization, Location, Concept, etc.
    description: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    source_chunk_id: Optional[str] = None
    confidence: float = 1.0


@dataclass
class Relationship:
    """Relationship between two entities."""

    source_entity: str
    target_entity: str
    relationship_type: str  # WORKS_AT, LOCATED_IN, RELATED_TO, etc.
    description: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


@dataclass
class ExtractionResult:
    """Result of entity extraction."""

    entities: List[Entity]
    relationships: List[Relationship]
    chunk_id: Optional[str] = None
    extraction_time_ms: float = 0


class EntityExtractionService:
    """
    Service for extracting entities and relationships from text.

    Uses Graphiti's LLM-based entity extraction when available,
    with fallback to basic NER patterns.

    Architecture:
    - Graphiti handles entity extraction and graph storage
    - Extracted entities are stored in Neo4j
    - Relationships enable multi-hop graph traversal

    Usage:
        extractor = EntityExtractionService()
        await extractor.initialize()
        result = await extractor.extract_entities("John works at Acme Corp in NYC.")
        # result.entities: [Person("John"), Organization("Acme Corp"), Location("NYC")]
        # result.relationships: [WORKS_AT(John, Acme Corp), LOCATED_IN(Acme Corp, NYC)]
    """

    def __init__(self):
        """Initialize entity extraction service."""
        self.settings = get_settings()
        self._graphiti_client = None
        self._llm_client = None
        self._initialized = False

    async def initialize(self):
        """Initialize Graphiti client and LLM."""
        if self._initialized:
            return

        try:
            await self._init_graphiti()
            self._initialized = True
            logger.info("✅ EntityExtractionService initialized")
        except Exception as e:
            logger.warning(f"⚠️ Graphiti unavailable, using basic extraction: {e}")
            self._initialized = True

    async def _init_graphiti(self):
        """Initialize Graphiti client for entity extraction."""
        try:
            from graphiti_core import Graphiti
            from graphiti_core.llm_client import OpenAIClient
            from graphiti_core.llm_client.config import LLMConfig
            import os

            # Configure LLM client
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

            self._llm_client = OpenAIClient(config=llm_config)

            # Connect to Neo4j
            self._graphiti_client = Graphiti(
                uri=self.settings.neo4j_uri,
                user=self.settings.neo4j_user,
                password=self.settings.neo4j_password,
                llm_client=self._llm_client,
            )

            # Ensure indices exist
            await self._graphiti_client.build_indices_and_constraints()
            logger.info("✅ Connected to Graphiti/Neo4j for entity extraction")

        except ImportError:
            logger.warning("⚠️ Graphiti not installed")
            self._graphiti_client = None
        except Exception as e:
            logger.warning(f"⚠️ Graphiti connection failed: {e}")
            self._graphiti_client = None

    async def extract_entities(
        self,
        text: str,
        chunk_id: Optional[str] = None,
        document_context: Optional[Dict[str, Any]] = None,
    ) -> ExtractionResult:
        """
        Extract entities and relationships from text.

        Args:
            text: Text to extract entities from
            chunk_id: Optional chunk ID for tracking
            document_context: Optional context (title, source, etc.)

        Returns:
            ExtractionResult with entities and relationships
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()

        if self._graphiti_client:
            result = await self._extract_with_graphiti(text, chunk_id, document_context)
        else:
            result = await self._extract_basic(text, chunk_id)

        result.extraction_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        logger.debug(
            f"🔍 Extracted {len(result.entities)} entities, "
            f"{len(result.relationships)} relationships in {result.extraction_time_ms:.0f}ms"
        )

        return result

    async def _extract_with_graphiti(
        self,
        text: str,
        chunk_id: Optional[str],
        document_context: Optional[Dict[str, Any]],
    ) -> ExtractionResult:
        """Extract entities using Graphiti's LLM-based extraction."""
        try:
            # Build episode name from context
            context = document_context or {}
            episode_name = context.get("title", f"chunk_{chunk_id or 'unknown'}")

            # Add episode to Graphiti (triggers entity extraction)
            episode = await self._graphiti_client.add_episode(
                name=episode_name,
                episode_body=text,
                reference_time=datetime.utcnow(),
                source_description=context.get("source", "document"),
            )

            # Query extracted entities from the episode
            # Graphiti stores entities in Neo4j automatically
            entities = []
            relationships = []

            # Get entities related to this episode
            if episode and hasattr(episode, 'entity_edges'):
                for edge in episode.entity_edges:
                    if hasattr(edge, 'source_node'):
                        entities.append(Entity(
                            name=edge.source_node.name,
                            entity_type=getattr(edge.source_node, 'labels', ['Entity'])[0],
                            description=getattr(edge.source_node, 'summary', None),
                            source_chunk_id=chunk_id,
                        ))

                    if hasattr(edge, 'target_node') and hasattr(edge, 'name'):
                        relationships.append(Relationship(
                            source_entity=edge.source_node.name,
                            target_entity=edge.target_node.name,
                            relationship_type=edge.name,
                        ))

            return ExtractionResult(
                entities=entities,
                relationships=relationships,
                chunk_id=chunk_id,
            )

        except Exception as e:
            logger.warning(f"⚠️ Graphiti extraction failed, using basic: {e}")
            return await self._extract_basic(text, chunk_id)

    async def _extract_basic(
        self,
        text: str,
        chunk_id: Optional[str],
    ) -> ExtractionResult:
        """
        Basic entity extraction using regex patterns.

        Fallback when Graphiti is unavailable.
        Extracts common patterns like emails, URLs, dates, etc.
        """
        import re

        entities = []
        relationships = []

        # Extract emails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        for match in re.finditer(email_pattern, text):
            entities.append(Entity(
                name=match.group(),
                entity_type="Email",
                source_chunk_id=chunk_id,
                confidence=0.9,
            ))

        # Extract URLs
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        for match in re.finditer(url_pattern, text):
            entities.append(Entity(
                name=match.group(),
                entity_type="URL",
                source_chunk_id=chunk_id,
                confidence=0.9,
            ))

        # Extract dates (basic patterns)
        date_patterns = [
            r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        ]
        for pattern in date_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                entities.append(Entity(
                    name=match.group(),
                    entity_type="Date",
                    source_chunk_id=chunk_id,
                    confidence=0.8,
                ))

        # Extract money amounts
        money_pattern = r'\$[\d,]+(?:\.\d{2})?(?:\s*(?:million|billion|thousand|[kmb]))?'
        for match in re.finditer(money_pattern, text, re.IGNORECASE):
            entities.append(Entity(
                name=match.group(),
                entity_type="Money",
                source_chunk_id=chunk_id,
                confidence=0.85,
            ))

        # Extract capitalized phrases (potential named entities)
        # This is a simple heuristic
        cap_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b'
        for match in re.finditer(cap_pattern, text):
            name = match.group()
            # Skip common words
            skip_words = {'The', 'This', 'That', 'These', 'Those', 'What', 'When', 'Where', 'Which', 'How'}
            if name.split()[0] not in skip_words:
                entities.append(Entity(
                    name=name,
                    entity_type="NamedEntity",
                    source_chunk_id=chunk_id,
                    confidence=0.5,  # Low confidence for basic extraction
                ))

        # Deduplicate by name
        seen_names = set()
        unique_entities = []
        for entity in entities:
            if entity.name.lower() not in seen_names:
                seen_names.add(entity.name.lower())
                unique_entities.append(entity)

        return ExtractionResult(
            entities=unique_entities,
            relationships=relationships,
            chunk_id=chunk_id,
        )

    async def extract_from_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_context: Optional[Dict[str, Any]] = None,
        max_concurrent: int = 3,
    ) -> List[ExtractionResult]:
        """
        Extract entities from multiple chunks concurrently.

        Args:
            chunks: List of chunk dicts with 'id' and 'content'
            document_context: Optional document-level context
            max_concurrent: Maximum concurrent extractions

        Returns:
            List of ExtractionResults
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def extract_with_limit(chunk: Dict[str, Any]):
            async with semaphore:
                return await self.extract_entities(
                    text=chunk.get("content", ""),
                    chunk_id=chunk.get("id"),
                    document_context=document_context,
                )

        results = await asyncio.gather(
            *[extract_with_limit(chunk) for chunk in chunks],
            return_exceptions=True,
        )

        # Filter out exceptions
        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"⚠️ Extraction failed for chunk {i}: {result}")
            else:
                valid_results.append(result)

        return valid_results

    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[Entity]:
        """
        Search for entities by name or description.

        Args:
            query: Search query
            entity_types: Optional filter by entity types
            limit: Maximum results

        Returns:
            List of matching entities
        """
        if not self._graphiti_client:
            logger.warning("⚠️ Entity search requires Graphiti")
            return []

        try:
            # Use Graphiti's search
            results = await self._graphiti_client.search(
                query=query,
                num_results=limit,
            )

            entities = []
            for result in results:
                if hasattr(result, 'node'):
                    node = result.node
                    entity_type = getattr(node, 'labels', ['Entity'])[0]

                    # Filter by type if specified
                    if entity_types and entity_type not in entity_types:
                        continue

                    entities.append(Entity(
                        name=node.name,
                        entity_type=entity_type,
                        description=getattr(node, 'summary', None),
                    ))

            return entities

        except Exception as e:
            logger.error(f"❌ Entity search failed: {e}")
            return []

    async def get_related_entities(
        self,
        entity_name: str,
        relationship_types: Optional[List[str]] = None,
        max_depth: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Get entities related to a given entity via graph traversal.

        Args:
            entity_name: Name of the source entity
            relationship_types: Optional filter by relationship types
            max_depth: Maximum traversal depth

        Returns:
            List of related entities with relationship info
        """
        if not self._graphiti_client:
            logger.warning("⚠️ Graph traversal requires Graphiti")
            return []

        try:
            # Query Neo4j for related entities
            # This uses Graphiti's underlying Neo4j connection
            related = []

            # Search for the entity first
            results = await self._graphiti_client.search(
                query=entity_name,
                num_results=1,
            )

            if results:
                # Get edges from the entity
                for result in results:
                    if hasattr(result, 'edges'):
                        for edge in result.edges:
                            rel_type = getattr(edge, 'name', 'RELATED_TO')

                            if relationship_types and rel_type not in relationship_types:
                                continue

                            related.append({
                                'entity': getattr(edge, 'target_node', {}).get('name', 'Unknown'),
                                'relationship': rel_type,
                                'depth': 1,
                            })

            return related

        except Exception as e:
            logger.error(f"❌ Graph traversal failed: {e}")
            return []

    async def close(self):
        """Close connections."""
        if self._graphiti_client:
            try:
                await self._graphiti_client.close()
            except Exception:
                pass
        self._initialized = False


# Singleton instance
_extractor: Optional[EntityExtractionService] = None


async def get_entity_extractor() -> EntityExtractionService:
    """Get or create the singleton entity extractor."""
    global _extractor
    if _extractor is None:
        _extractor = EntityExtractionService()
        await _extractor.initialize()
    return _extractor

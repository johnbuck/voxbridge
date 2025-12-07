"""
Graph API Routes (RAG Phase 3.1d)

FastAPI routes for knowledge graph visualization and entity management.
"""

import logging
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field

from ..services.storage import get_storage_service

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================


class GraphNode(BaseModel):
    """A node in the knowledge graph."""

    id: str
    label: str
    entity_type: str
    properties: dict = Field(default_factory=dict)
    summary: Optional[str] = None


class GraphEdge(BaseModel):
    """An edge/relationship in the knowledge graph."""

    id: str
    source: str
    target: str
    label: str
    properties: dict = Field(default_factory=dict)


class GraphData(BaseModel):
    """Graph data for visualization."""

    nodes: List[GraphNode]
    edges: List[GraphEdge]


class EntitySearchResponse(BaseModel):
    """Entity search results."""

    entities: List[GraphNode]
    count: int


# ============================================================================
# Router Setup
# ============================================================================

router = APIRouter(prefix="/api/graph", tags=["graph"])


# ============================================================================
# Graph Routes
# ============================================================================


@router.get(
    "/entities",
    response_model=EntitySearchResponse,
    summary="Search Entities",
    description="Search for entities in the knowledge graph"
)
async def search_entities(
    query: Optional[str] = Query(None, description="Search query"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
):
    """
    Search for entities in the knowledge graph.

    Returns matching entities from Neo4j/Graphiti.
    """
    try:
        storage = await get_storage_service()

        if not storage._graphiti_client:
            return EntitySearchResponse(entities=[], count=0)

        # Search for entities
        entities = []

        if query:
            # Use Graphiti search
            results = await storage._graphiti_client.search(
                query=query,
                num_results=limit,
            )

            for result in results:
                # Extract node info
                if hasattr(result, 'uuid'):
                    entities.append(GraphNode(
                        id=str(result.uuid),
                        label=getattr(result, 'name', 'Unknown'),
                        entity_type=getattr(result, 'labels', ['Entity'])[0] if hasattr(result, 'labels') else 'Entity',
                        summary=getattr(result, 'summary', None),
                        properties={
                            'created_at': str(getattr(result, 'created_at', '')),
                        },
                    ))
        else:
            # Get recent entities using Cypher query
            driver = storage._graphiti_client._driver if hasattr(storage._graphiti_client, '_driver') else None

            if driver:
                async with driver.session() as session:
                    result = await session.run(
                        """
                        MATCH (n:Entity)
                        RETURN n.uuid as id, n.name as name, labels(n) as labels,
                               n.summary as summary, n.created_at as created_at
                        ORDER BY n.created_at DESC
                        LIMIT $limit
                        """,
                        {"limit": limit}
                    )

                    records = await result.data()
                    for record in records:
                        entity_labels = record.get('labels', ['Entity'])
                        # Filter out 'Entity' base label to get specific type
                        specific_types = [l for l in entity_labels if l != 'Entity']
                        entity_type = specific_types[0] if specific_types else 'Entity'

                        entities.append(GraphNode(
                            id=str(record.get('id', '')),
                            label=record.get('name', 'Unknown'),
                            entity_type=entity_type,
                            summary=record.get('summary'),
                            properties={
                                'created_at': str(record.get('created_at', '')),
                            },
                        ))

        return EntitySearchResponse(entities=entities, count=len(entities))

    except Exception as e:
        logger.error(f"Entity search failed: {e}")
        return EntitySearchResponse(entities=[], count=0)


@router.get(
    "/subgraph",
    response_model=GraphData,
    summary="Get Subgraph",
    description="Get a subgraph centered on an entity"
)
async def get_subgraph(
    entity_id: Optional[str] = Query(None, description="Center entity UUID"),
    query: Optional[str] = Query(None, description="Search query to find center"),
    depth: int = Query(2, ge=1, le=4, description="Traversal depth"),
    limit: int = Query(100, ge=1, le=500, description="Max nodes"),
):
    """
    Get a subgraph from the knowledge graph.

    Returns nodes and edges for visualization with React Flow.
    """
    try:
        storage = await get_storage_service()

        if not storage._graphiti_client:
            return GraphData(nodes=[], edges=[])

        driver = storage._graphiti_client._driver if hasattr(storage._graphiti_client, '_driver') else None

        if not driver:
            return GraphData(nodes=[], edges=[])

        nodes = []
        edges = []

        async with driver.session() as session:
            if entity_id:
                # Get subgraph around specific entity
                result = await session.run(
                    """
                    MATCH path = (center:Entity {uuid: $entity_id})-[*1..$depth]-(related:Entity)
                    WITH nodes(path) as ns, relationships(path) as rs
                    UNWIND ns as n
                    WITH DISTINCT n, rs
                    RETURN n.uuid as id, n.name as name, labels(n) as labels, n.summary as summary
                    LIMIT $limit
                    """,
                    {"entity_id": entity_id, "depth": depth, "limit": limit}
                )
                node_records = await result.data()

                for record in node_records:
                    entity_labels = record.get('labels', ['Entity'])
                    specific_types = [l for l in entity_labels if l != 'Entity']
                    entity_type = specific_types[0] if specific_types else 'Entity'

                    nodes.append(GraphNode(
                        id=str(record.get('id', '')),
                        label=record.get('name', 'Unknown'),
                        entity_type=entity_type,
                        summary=record.get('summary'),
                    ))

                # Get edges
                edge_result = await session.run(
                    """
                    MATCH (center:Entity {uuid: $entity_id})-[r]-(related:Entity)
                    RETURN r.uuid as id, startNode(r).uuid as source, endNode(r).uuid as target,
                           type(r) as type, r.name as name
                    LIMIT $limit
                    """,
                    {"entity_id": entity_id, "limit": limit}
                )
                edge_records = await edge_result.data()

                for record in edge_records:
                    edges.append(GraphEdge(
                        id=str(record.get('id', '')),
                        source=str(record.get('source', '')),
                        target=str(record.get('target', '')),
                        label=record.get('name') or record.get('type', 'RELATES_TO'),
                    ))

            else:
                # Get overview graph (recent entities and their relationships)
                result = await session.run(
                    """
                    MATCH (n:Entity)
                    WITH n ORDER BY n.created_at DESC LIMIT $limit
                    OPTIONAL MATCH (n)-[r:RELATES_TO]-(m:Entity)
                    RETURN n.uuid as id, n.name as name, labels(n) as labels, n.summary as summary,
                           collect(DISTINCT {
                               id: r.uuid,
                               source: startNode(r).uuid,
                               target: endNode(r).uuid,
                               type: type(r),
                               name: r.name
                           }) as rels
                    """,
                    {"limit": limit}
                )
                records = await result.data()

                seen_edges = set()
                for record in records:
                    entity_labels = record.get('labels', ['Entity'])
                    specific_types = [l for l in entity_labels if l != 'Entity']
                    entity_type = specific_types[0] if specific_types else 'Entity'

                    nodes.append(GraphNode(
                        id=str(record.get('id', '')),
                        label=record.get('name', 'Unknown'),
                        entity_type=entity_type,
                        summary=record.get('summary'),
                    ))

                    for rel in record.get('rels', []):
                        if rel.get('id') and rel['id'] not in seen_edges:
                            seen_edges.add(rel['id'])
                            edges.append(GraphEdge(
                                id=str(rel['id']),
                                source=str(rel.get('source', '')),
                                target=str(rel.get('target', '')),
                                label=rel.get('name') or rel.get('type', 'RELATES_TO'),
                            ))

        return GraphData(nodes=nodes, edges=edges)

    except Exception as e:
        logger.error(f"Subgraph query failed: {e}")
        return GraphData(nodes=[], edges=[])


@router.get(
    "/stats",
    summary="Graph Statistics",
    description="Get statistics about the knowledge graph"
)
async def get_graph_stats():
    """
    Get statistics about the knowledge graph.
    """
    try:
        storage = await get_storage_service()

        if not storage._graphiti_client:
            return {
                "connected": False,
                "node_count": 0,
                "edge_count": 0,
                "entity_types": [],
            }

        driver = storage._graphiti_client._driver if hasattr(storage._graphiti_client, '_driver') else None

        if not driver:
            return {
                "connected": True,
                "node_count": 0,
                "edge_count": 0,
                "entity_types": [],
            }

        async with driver.session() as session:
            # Get node count
            node_result = await session.run("MATCH (n:Entity) RETURN count(n) as count")
            node_record = await node_result.single()
            node_count = node_record['count'] if node_record else 0

            # Get edge count
            edge_result = await session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            edge_record = await edge_result.single()
            edge_count = edge_record['count'] if edge_record else 0

            # Get entity types
            type_result = await session.run("""
                MATCH (n:Entity)
                WITH labels(n) as ls
                UNWIND ls as label
                WHERE label <> 'Entity'
                RETURN DISTINCT label, count(*) as count
                ORDER BY count DESC
            """)
            type_records = await type_result.data()
            entity_types = [{"type": r['label'], "count": r['count']} for r in type_records]

            return {
                "connected": True,
                "node_count": node_count,
                "edge_count": edge_count,
                "entity_types": entity_types,
            }

    except Exception as e:
        logger.error(f"Graph stats query failed: {e}")
        return {
            "connected": False,
            "error": str(e),
            "node_count": 0,
            "edge_count": 0,
            "entity_types": [],
        }

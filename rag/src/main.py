"""
VoxBridge RAG Service

Standalone FastAPI service for document ingestion, hybrid retrieval, and RAG.
Provides vector search, BM25 keyword search, and optional knowledge graph integration.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database.session import init_db, close_db
from .routes import collection_routes, search, graph

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("🚀 Starting VoxBridge RAG Service...")

    settings = get_settings()
    logger.info(f"📊 Embedding model: {settings.embedding_model}")
    logger.info(f"📊 Reranker model: {settings.reranker_model}")
    logger.info(f"📊 Chunk size: {settings.chunk_size} tokens")

    # Initialize database
    await init_db()
    logger.info("✅ Database connection established")

    # Initialize services (lazy loading)
    try:
        from .services.retrieval import get_retrieval_service
        await get_retrieval_service()
        logger.info("✅ Retrieval service initialized")
    except Exception as e:
        logger.warning(f"⚠️ Retrieval service initialization deferred: {e}")

    # Check Neo4j connection (optional)
    if settings.neo4j_uri:
        try:
            from .services.storage import get_storage_service
            storage = await get_storage_service()
            if storage._graphiti_client:
                logger.info("✅ Neo4j/Graphiti connection established")
            else:
                logger.info("ℹ️ Neo4j not configured, graph search disabled")
        except Exception as e:
            logger.warning(f"⚠️ Neo4j connection failed (optional): {e}")

    logger.info("✅ VoxBridge RAG Service ready")

    yield

    # Shutdown
    logger.info("🛑 Shutting down VoxBridge RAG Service...")
    await close_db()
    logger.info("✅ Database connections closed")


# Create FastAPI app
app = FastAPI(
    title="VoxBridge RAG Service",
    description="Document ingestion, hybrid retrieval, and RAG for VoxBridge",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(collection_routes.router)
app.include_router(search.router)
app.include_router(graph.router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    settings = get_settings()

    # Check database
    db_healthy = False
    try:
        from sqlalchemy import text
        from .database.session import get_db_session
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
            db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    # Check Neo4j (optional)
    neo4j_healthy = None
    if settings.neo4j_uri:
        try:
            from .services.storage import get_storage_service
            storage = await get_storage_service()
            neo4j_healthy = storage._graphiti_client is not None
        except Exception:
            neo4j_healthy = False

    # Check retrieval service
    retrieval_healthy = False
    try:
        from .services.retrieval import get_retrieval_service
        retrieval = await get_retrieval_service()
        retrieval_healthy = retrieval._embedding_model is not None
    except Exception:
        pass

    status = "healthy" if db_healthy and retrieval_healthy else "degraded"
    if not db_healthy:
        status = "unhealthy"

    return {
        "status": status,
        "service": "voxbridge-rag",
        "version": "1.0.0",
        "components": {
            "database": db_healthy,
            "neo4j": neo4j_healthy,
            "retrieval": retrieval_healthy,
        },
        "config": {
            "embedding_model": settings.embedding_model,
            "reranker_model": settings.reranker_model,
            "chunk_size": settings.chunk_size,
        }
    }


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "VoxBridge RAG Service",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "collections": "/api/collections",
            "search": "/api/search",
            "context": "/api/context",
            "graph_entities": "/api/graph/entities",
            "graph_subgraph": "/api/graph/subgraph",
            "graph_stats": "/api/graph/stats",
        }
    }

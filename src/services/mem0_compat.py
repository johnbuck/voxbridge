"""
Mem0 API Compatibility Layer for VoxBridge

Normalizes inconsistent response formats between Mem0 v1.0.1 methods:
- memory.add() returns {"results": [...]}
- memory.search() returns [{...}, {...}] (raw list)

This layer ensures consistent handling across all code paths and provides
forward compatibility with Mem0 v1.1+ where all methods will return dict format.

Author: VoxBridge Team
Date: 2025-11-28
"""
from typing import List, Dict, Any, Optional
from src.config.logging_config import get_logger

logger = get_logger(__name__)


class Mem0ResponseNormalizer:
    """
    Normalizes Mem0 API responses to consistent format.

    All methods return: List[Dict[str, Any]]
    Each dict has standardized keys:
      - id: str - Vector ID
      - text: str - Fact content
      - score: float - Relevance score (0.0-1.0)
      - event: str - Event type (ADD/UPDATE/DELETE/NONE)
      - metadata: dict - Additional metadata
    """

    @staticmethod
    def normalize_add_response(response: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize memory.add() response.

        Mem0 v1.0.1 format:
            {"results": [{"id": "...", "memory": "...", "event": "ADD"}]}

        Mem0 v1.1+ format (future):
            {"results": [{"id": "...", "text": "...", "event": "ADD"}]}

        Returns:
            [{"id": "...", "text": "...", "event": "ADD", "score": 0.0, "metadata": {}}]

        Example:
            >>> response = {"results": [{"id": "vec1", "memory": "Portland", "event": "ADD"}]}
            >>> Mem0ResponseNormalizer.normalize_add_response(response)
            [{'id': 'vec1', 'text': 'Portland', 'event': 'ADD', 'score': 0.0, 'metadata': {}}]
        """
        if not response:
            logger.debug("🔄 [MEM0_COMPAT] add() returned empty response")
            return []

        # v1.0.1 and v1.1+: {"results": [...]}
        if isinstance(response, dict) and "results" in response:
            results = response["results"]
            if not results:
                logger.debug("🔄 [MEM0_COMPAT] add() returned empty results list")
                return []

            normalized = []
            for item in results:
                if not isinstance(item, dict):
                    logger.warning(f"⚠️ [MEM0_COMPAT] Unexpected item type in add() results: {type(item)}")
                    continue

                # Extract text from "memory" (v1.0.1) or "text"/"data" (v1.1+)
                text = item.get("memory") or item.get("text") or item.get("data") or ""

                normalized_item = {
                    "id": item.get("id", ""),
                    "text": text,
                    "event": item.get("event", "UNKNOWN"),
                    "score": item.get("score", 0.0),
                    "metadata": item.get("metadata", {})
                }
                normalized.append(normalized_item)

            logger.debug(
                f"✅ [MEM0_COMPAT] Normalized add() response: {len(normalized)} items "
                f"(format: dict with 'results' key)"
            )
            return normalized

        # Fallback for unexpected format
        logger.warning(
            f"⚠️ [MEM0_COMPAT] Unexpected add() response format: {type(response)}. "
            f"Expected dict with 'results' key."
        )
        return []

    @staticmethod
    def normalize_search_response(response: Any) -> List[Dict[str, Any]]:
        """
        Normalize memory.search() response.

        Mem0 v1.0.1 format (CURRENT):
            [{"id": "...", "memory": "...", "score": 0.95}]  # Raw list!

        Mem0 v1.1+ format (FUTURE):
            {"results": [{"id": "...", "data": "...", "score": 0.95}]}

        Returns:
            [{"id": "...", "text": "...", "score": 0.95, "event": "NONE", "metadata": {}}]

        Example:
            >>> response = [{"id": "vec1", "memory": "Portland", "score": 0.95}]
            >>> Mem0ResponseNormalizer.normalize_search_response(response)
            [{'id': 'vec1', 'text': 'Portland', 'score': 0.95, 'event': 'NONE', 'metadata': {}}]
        """
        if not response:
            logger.debug("🔄 [MEM0_COMPAT] search() returned empty response")
            return []

        # v1.1+ future format: {"results": [...]}
        if isinstance(response, dict) and "results" in response:
            results = response["results"]
            if not results:
                logger.debug("🔄 [MEM0_COMPAT] search() returned empty results list")
                return []

            normalized = []
            for item in results:
                if not isinstance(item, dict):
                    # Handle string-only results (some Mem0 versions)
                    normalized.append({
                        "id": "",
                        "text": str(item),
                        "score": 0.0,
                        "event": "NONE",
                        "metadata": {}
                    })
                    continue

                # v1.1+ uses "data" field
                text = item.get("data") or item.get("memory") or item.get("text") or ""

                normalized_item = {
                    "id": item.get("id", ""),
                    "text": text,
                    "score": item.get("score", 0.0),
                    "event": "NONE",  # search() doesn't return event type
                    "metadata": item.get("metadata", {})
                }
                normalized.append(normalized_item)

            logger.debug(
                f"✅ [MEM0_COMPAT] Normalized search() response: {len(normalized)} items "
                f"(format: dict with 'results' key - v1.1+ detected)"
            )
            return normalized

        # v1.0.1 current format: [{...}, {...}] (raw list)
        if isinstance(response, list):
            if not response:
                logger.debug("🔄 [MEM0_COMPAT] search() returned empty list")
                return []

            normalized = []
            for item in response:
                if isinstance(item, str):
                    # String-only result
                    normalized.append({
                        "id": "",
                        "text": item,
                        "score": 0.0,
                        "event": "NONE",
                        "metadata": {}
                    })
                    continue

                if not isinstance(item, dict):
                    logger.warning(f"⚠️ [MEM0_COMPAT] Unexpected item type in search() list: {type(item)}")
                    continue

                # v1.0.1 uses "memory" field (prioritize this for current version)
                text = item.get("memory") or item.get("data") or item.get("text") or ""

                normalized_item = {
                    "id": item.get("id", ""),
                    "text": text,
                    "score": item.get("score", 0.0),
                    "event": "NONE",
                    "metadata": item.get("metadata", {})
                }
                normalized.append(normalized_item)

            logger.debug(
                f"✅ [MEM0_COMPAT] Normalized search() response: {len(normalized)} items "
                f"(format: raw list - v1.0.1 detected)"
            )
            return normalized

        # Fallback for unexpected format
        logger.warning(
            f"⚠️ [MEM0_COMPAT] Unexpected search() response format: {type(response)}. "
            f"Expected list or dict with 'results' key."
        )
        return []

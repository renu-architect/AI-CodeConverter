"""DiskCache wrapper for LLM response caching."""

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from diskcache import Cache

from utils.logging import get_logger

logger = get_logger("gateway.cache")


class GatewayCache:
    """Hash-based cache for gateway responses."""

    def __init__(self, directory: str, ttl_seconds: int = 86400, enabled: bool = True) -> None:
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self._cache: Optional[Cache] = None
        if enabled:
            cache_dir = Path(directory) / "gateway"
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache = Cache(str(cache_dir))

    @staticmethod
    def compute_key(prompt: str, context: str) -> str:
        """Compute SHA-256 cache key from prompt and context."""
        combined = f"{prompt}||{context}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, key: str) -> Optional[dict[str, Any]]:
        """Retrieve cached response if exists."""
        if not self.enabled or self._cache is None:
            return None
        result = self._cache.get(key)
        if result is not None:
            logger.info("Cache hit", extra={"cache_key": key[:16]})
        return result

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Store response in cache."""
        if not self.enabled or self._cache is None:
            return
        self._cache.set(key, value, expire=self.ttl_seconds)
        logger.info("Cache store", extra={"cache_key": key[:16]})

    def clear(self) -> None:
        """Clear all cached entries."""
        if self._cache is not None:
            self._cache.clear()

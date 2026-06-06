"""
Caching utility for TradeCraft.
Supports Redis when available, falls back to in-memory LRU for development.
"""

import os
import logging
import json
import hashlib
from typing import Optional, Any, Callable
from functools import wraps

logger = logging.getLogger(__name__)

# Try to import redis
REDIS_AVAILABLE = False
redis_client = None
try:
    import redis
    _redis_url = os.getenv("REDIS_URL")
    if _redis_url:
        redis_client = redis.from_url(_redis_url, decode_responses=True)
        REDIS_AVAILABLE = True
        logger.info("Redis cache initialized: %s", _redis_url)
    else:
        logger.info("REDIS_URL not set; using in-memory fallback caching")
except ImportError:
    logger.info("redis package not installed; using in-memory fallback caching")
except Exception as e:
    logger.warning("Failed to connect to Redis: %s; using in-memory fallback", e)


class InMemoryCache:
    """Simple in-memory LRU cache fallback."""
    
    def __init__(self, maxsize: int = 128):
        self._store: dict = {}
        self._maxsize = maxsize
    
    def get(self, key: str) -> Optional[str]:
        return self._store.get(key)
    
    def set(self, key: str, value: str, ex: Optional[int] = None):
        # Simple eviction: remove oldest if at capacity
        if len(self._store) >= self._maxsize and key not in self._store:
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[key] = value
    
    def delete(self, key: str):
        self._store.pop(key, None)
    
    def flushdb(self):
        self._store.clear()


# Use Redis if available, else in-memory
_cache_backend = redis_client if REDIS_AVAILABLE else InMemoryCache()


def _generate_key(prefix: str, *args, **kwargs) -> str:
    """Generate a deterministic cache key from arguments."""
    payload = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
    hash_digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"tradecraft:{prefix}:{hash_digest}"


def cached(prefix: str, ttl_seconds: int = 300):
    """
    Decorator to cache function results.
    
    Args:
        prefix: Namespace prefix for cache keys
        ttl_seconds: Time-to-live in seconds (ignored for in-memory)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = _generate_key(prefix, *args, **kwargs)
            try:
                cached_value = _cache_backend.get(key)
                if cached_value is not None:
                    return json.loads(cached_value)
            except Exception as e:
                logger.debug("Cache read error for key %s: %s", key, e)
            
            result = func(*args, **kwargs)
            
            try:
                serialized = json.dumps(result, default=str)
                _cache_backend.set(key, serialized, ex=ttl_seconds)
            except Exception as e:
                logger.debug("Cache write error for key %s: %s", key, e)
            
            return result
        return wrapper
    return decorator


def cache_get(key: str) -> Optional[Any]:
    """Get a value from cache by key."""
    try:
        value = _cache_backend.get(key)
        if value is not None:
            return json.loads(value)
    except Exception as e:
        logger.debug("Cache get error: %s", e)
    return None


def cache_set(key: str, value: Any, ttl_seconds: int = 300):
    """Set a value in cache."""
    try:
        serialized = json.dumps(value, default=str)
        _cache_backend.set(key, serialized, ex=ttl_seconds)
    except Exception as e:
        logger.debug("Cache set error: %s", e)


def cache_delete(key: str):
    """Delete a key from cache."""
    try:
        _cache_backend.delete(key)
    except Exception as e:
        logger.debug("Cache delete error: %s", e)

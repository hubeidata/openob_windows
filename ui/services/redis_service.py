# -*- coding: utf-8 -*-
"""
redis_service.py - Redis connection and VU data operations.

Design decisions:
- Encapsulates all Redis operations
- Returns typed data (VUData) or None on failure
- Handles connection lifecycle and reconnection
- Separates connection from data fetching
"""

from __future__ import annotations

import re
import time
import logging
from dataclasses import dataclass
from typing import Optional, Tuple, Any

try:
    import redis
    HAS_REDIS = True
except ImportError:
    redis = None
    HAS_REDIS = False


logger = logging.getLogger('openob.ui.redis')


@dataclass
class VUData:
    """VU data fetched from Redis."""
    left_db: float
    right_db: float
    timestamp: Optional[float] = None
    is_stale: bool = False


class RedisService:
    """
    Service for Redis operations.
    
    Handles connection management and VU data fetching from Redis.
    """
    
    # Data staleness threshold in seconds
    STALE_THRESHOLD = 5.0
    
    def __init__(self):
        self._client: Optional[Any] = None  # redis.StrictRedis
        self._host: Optional[str] = None
        self._port: int = 6379
    
    @property
    def is_available(self) -> bool:
        """Check if Redis library is available."""
        return HAS_REDIS
    
    @property
    def is_connected(self) -> bool:
        """Check if currently connected to Redis."""
        return self._client is not None
    
    def connect(self, host: str, port: int = 6379) -> bool:
        """
        Connect to Redis server.
        
        Args:
            host: Redis host address
            port: Redis port (default 6379)
            
        Returns:
            True if connection successful, False otherwise
        """
        if not HAS_REDIS:
            logger.warning("Redis library not available")
            return False
        
        # Already connected to same host:port
        if self._client and self._host == host and self._port == port:
            return True
        
        try:
            client = redis.StrictRedis(
                host=host, 
                port=port, 
                db=0, 
                charset='utf-8', 
                decode_responses=True
            )
            client.ping()
            
            self._client = client
            self._host = host
            self._port = port
            logger.info(f"Connected to Redis at {host}:{port}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to connect to Redis at {host}:{port}: {e}")
            self._client = None
            return False
    
    def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._client = None
        self._host = None
        self._port = 6379
    
    def fetch_vu_data(self, link_name: str, role: str) -> Optional[VUData]:
        """
        Fetch VU data from Redis.
        
        Args:
            link_name: OpenOB link name
            role: 'tx' for transmitter or 'rx' for receiver
            
        Returns:
            VUData if successful, None otherwise
        """
        if not self._client:
            return None
        
        key = f'openob:{link_name}:vu:{role}'
        
        try:
            data = self._client.hgetall(key)
        except Exception as e:
            logger.warning(f"Failed to fetch VU data from {key}: {e}")
            return None
        
        if not data:
            return None
        
        # Parse left/right values
        left, right = self._parse_vu_values(data)
        
        if left is None or right is None:
            return None
        
        # Check timestamp for staleness
        timestamp = self._parse_timestamp(data)
        is_stale = False
        if timestamp is not None:
            age = time.time() - timestamp
            if age > self.STALE_THRESHOLD:
                is_stale = True
        
        return VUData(
            left_db=left,
            right_db=right,
            timestamp=timestamp,
            is_stale=is_stale
        )
    
    def _parse_vu_values(self, data: dict) -> Tuple[Optional[float], Optional[float]]:
        """Parse left/right dB values from Redis hash data."""
        left = data.get('left_db') or data.get('left') or data.get('l')
        right = data.get('right_db') or data.get('right') or data.get('r')
        
        # Try combined field if individual not found
        if left is None and right is None:
            combined = data.get('audio_level_db') or data.get('audio_level') or data.get('level')
            if combined:
                nums = re.findall(r'-?\d+(?:\.\d+)?', str(combined))
                if len(nums) >= 2:
                    left, right = nums[-2], nums[-1]
                elif len(nums) == 1:
                    left = right = nums[0]
        
        # Convert to float
        try:
            left_val = float(left) if left is not None else None
            right_val = float(right) if right is not None else left_val
            return left_val, right_val
        except (ValueError, TypeError):
            return None, None
    
    def _parse_timestamp(self, data: dict) -> Optional[float]:
        """Parse timestamp from Redis hash data."""
        ts = data.get('updated_ts') or data.get('ts')
        if ts is not None:
            try:
                return float(ts)
            except (ValueError, TypeError):
                pass
        return None
    
    @staticmethod
    def parse_host_port(raw_host: str) -> Tuple[Optional[str], int]:
        """
        Parse host:port string.
        
        Args:
            raw_host: String like "127.0.0.1" or "127.0.0.1:6379"
            
        Returns:
            Tuple of (host, port)
        """
        if not raw_host:
            return None, 6379
        
        if ':' in raw_host:
            parts = raw_host.split(':', 1)
            try:
                return parts[0], int(parts[1])
            except ValueError:
                return parts[0], 6379
        
        return raw_host, 6379

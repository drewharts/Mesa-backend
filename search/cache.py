import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from search.base import SearchResult

logger = logging.getLogger(__name__)

class PlacesCache:
    def __init__(self, cache_duration: int = 3600):  # Default cache duration: 1 hour
        self.cache: Dict[str, Tuple[List[SearchResult], datetime]] = {}
        self.cache_duration = cache_duration
        self.session_token = None
        self.session_token_time = None
        
    def _generate_cache_key(self, query: str, latitude: Optional[float], longitude: Optional[float]) -> str:
        """Generate a cache key based on search parameters"""
        loc_str = f"{latitude},{longitude}" if latitude is not None and longitude is not None else "no-loc"
        return f"{query}:{loc_str}"
        
    def get(self, query: str, latitude: Optional[float], longitude: Optional[float]) -> Optional[List[SearchResult]]:
        """Get cached results if they exist and are not expired"""
        cache_key = self._generate_cache_key(query, latitude, longitude)
        if cache_key in self.cache:
            results, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_duration):
                return results
        return None
        
    def set(self, query: str, latitude: Optional[float], longitude: Optional[float], results: List[SearchResult]):
        """Cache the results with current timestamp"""
        cache_key = self._generate_cache_key(query, latitude, longitude)
        self.cache[cache_key] = (results, datetime.now())
        
    def get_session_token(self) -> str:
        """Get or generate a new session token"""
        current_time = time.time()
        if (self.session_token is None or 
            self.session_token_time is None or 
            current_time - self.session_token_time > 300):  # 5 minutes
            self.session_token = str(int(current_time))
            self.session_token_time = current_time
        return self.session_token 
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from search.detail_place import DetailPlace
from search.search_result import SearchResult

class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        """Search for places matching the query."""
        pass
        
    @abstractmethod
    def get_place_details(self, place_id: str) -> DetailPlace:
        """Get detailed information about a specific place."""
        pass 
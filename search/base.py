from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class SearchResult:
    def __init__(self, name: str, address: str, latitude: float, longitude: float, 
                 source: str, place_id: str = None, additional_data: Dict = None):
        self.name = name
        self.address = address
        self.latitude = latitude
        self.longitude = longitude
        self.source = source
        self.place_id = place_id
        self.additional_data = additional_data or {}

class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        """Search for places matching the query."""
        pass
        
    @abstractmethod
    def get_place_details(self, place_id: str) -> SearchResult:
        """Get detailed information about a specific place."""
        pass 
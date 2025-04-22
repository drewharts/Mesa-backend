import logging
from typing import List, Dict, Any, Optional

from search.base import SearchProvider, SearchResult
from search.whoosh_provider import WhooshSearchProvider
from search.mapbox_provider import MapboxSearchProvider
from search.google_provider import GooglePlacesSearchProvider

logger = logging.getLogger(__name__)

class SearchOrchestrator:
    def __init__(self, whoosh_provider: WhooshSearchProvider,
                 mapbox_provider: MapboxSearchProvider,
                 google_places_provider: GooglePlacesSearchProvider):
        self.whoosh_provider = whoosh_provider
        self.mapbox_provider = mapbox_provider
        self.google_places_provider = google_places_provider

    def _is_same_place(self, place1: SearchResult, place2: SearchResult) -> bool:
        """Check if two places are likely the same based on name and address."""
        # Normalize names and addresses for comparison
        name1 = place1.name.lower().strip()
        name2 = place2.name.lower().strip()
        
        # If names are exactly the same
        if name1 == name2:
            # Check if addresses are similar (allowing for different formatting)
            addr1 = place1.address.lower().strip()
            addr2 = place2.address.lower().strip()
            
            # Remove common variations
            for suffix in [', usa', ', united states', ', ut', ', utah']:
                addr1 = addr1.replace(suffix, '')
                addr2 = addr2.replace(suffix, '')
            
            # If addresses are similar after normalization
            if addr1 == addr2:
                return True
                
        return False

    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        # Try Whoosh first
        whoosh_results = self.whoosh_provider.search(query, limit)
        
        # If we have 5 or more results from Whoosh, return them
        if len(whoosh_results) >= 5:
            return whoosh_results
            
        # If we have fewer than 5 results, try Mapbox
        mapbox_results = self.mapbox_provider.search(query, limit - len(whoosh_results), latitude, longitude)
        
        # Combine results from both providers with deduplication
        combined_results = whoosh_results.copy()
        for mapbox_result in mapbox_results:
            # Check if this result is a duplicate
            is_duplicate = any(self._is_same_place(mapbox_result, existing) for existing in combined_results)
            if not is_duplicate:
                combined_results.append(mapbox_result)
        
        # If we still don't have enough results, try Google Places
        if len(combined_results) < 5:
            google_results = self.google_places_provider.search(query, limit - len(combined_results), latitude, longitude)
            for google_result in google_results:
                # Check if this result is a duplicate
                is_duplicate = any(self._is_same_place(google_result, existing) for existing in combined_results)
                if not is_duplicate:
                    combined_results.append(google_result)
            
        return combined_results 
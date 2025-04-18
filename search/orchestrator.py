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

    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        # Try Whoosh first
        whoosh_results = self.whoosh_provider.search(query, limit)
        
        # If we have 5 or more results from Whoosh, return them
        if len(whoosh_results) >= 5:
            return whoosh_results
            
        # If we have fewer than 5 results, try Mapbox
        mapbox_results = self.mapbox_provider.search(query, limit - len(whoosh_results), latitude, longitude)
        
        # Combine results from both providers
        combined_results = whoosh_results + mapbox_results
        
        # If we still don't have enough results, try Google Places
        if len(combined_results) < 5:
            google_results = self.google_places_provider.search(query, limit - len(combined_results), latitude, longitude)
            combined_results.extend(google_results)
            
        return combined_results 
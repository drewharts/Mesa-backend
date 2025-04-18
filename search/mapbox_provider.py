import logging
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from search.base import SearchProvider, SearchResult
from search.storage import PlaceStorage
from search.cache import PlacesCache

logger = logging.getLogger(__name__)

class MapboxSearchProvider(SearchProvider):
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.mapbox.com/search/searchbox/v1"
        self.storage = PlaceStorage()
        self.cache = PlacesCache()

    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        params = {
            "access_token": self.access_token,
            "q": query,
            "limit": limit,
            "language": "en",
            "country": "US",
            "types": "poi",
            "session_token": self.cache.get_session_token() if hasattr(self, 'cache') else None
        }
        
        # Add proximity if coordinates are provided
        if latitude is not None and longitude is not None:
            params["proximity"] = f"{longitude},{latitude}"
        
        # Remove None values from params
        params = {k: v for k, v in params.items() if v is not None}
        
        logger.debug(f"Mapbox search params: {params}")
        url = f"{self.base_url}/suggest"
        logger.debug(f"Mapbox API URL: {url}")
        
        try:
            response = requests.get(url, params=params)
            logger.debug(f"Mapbox API Response Status: {response.status_code}")
            logger.debug(f"Mapbox API Response Headers: {response.headers}")
            logger.debug(f"Mapbox API URL: {url}")
            logger.debug(f"Mapbox API Params: {params}")
            
            if response.status_code != 200:
                logger.error(f"Mapbox API Error: {response.text}")
                return []
                
            response.raise_for_status()
            data = response.json()
            
            logger.debug(f"Mapbox response data: {data}")
            
            # Log the first suggestion's structure for debugging
            if data.get("suggestions"):
                first_suggestion = data["suggestions"][0]
                logger.debug(f"First suggestion structure: {first_suggestion}")
                if "point" in first_suggestion:
                    logger.debug(f"Point data: {first_suggestion['point']}")
            
            # Use a dictionary to track unique results by mapbox_id and name+address combination
            unique_results = {}
            seen_places = set()  # Track unique name+address combinations
            
            for suggestion in data.get("suggestions", []):
                # Get the mapbox_id first to check for duplicates
                mapbox_id = suggestion.get("mapbox_id")
                if not mapbox_id:
                    continue
                
                # Get the name and full address
                name = suggestion.get("name", "")
                full_address = suggestion.get("place_formatted", "")
                
                # Create a unique key combining name and address
                place_key = f"{name.lower()}|{full_address.lower()}"
                
                # Skip if we've seen this place before (either by ID or name+address)
                if mapbox_id in unique_results or place_key in seen_places:
                    continue
                
                # Get coordinates if available
                point = suggestion.get("point", {})
                coordinates = point.get("coordinates", [])
                # Mapbox returns coordinates as [longitude, latitude]
                longitude = coordinates[0] if coordinates and len(coordinates) > 0 else 0.0
                latitude = coordinates[1] if coordinates and len(coordinates) > 1 else 0.0
                
                # Log the coordinates for debugging
                logger.debug(f"Extracted coordinates for {name}: lat={latitude}, lng={longitude}")
                
                search_result = SearchResult(
                    name=name,
                    address=full_address,
                    latitude=latitude,
                    longitude=longitude,
                    place_id=mapbox_id,
                    source="mapbox",
                    additional_data=suggestion
                )
                
                # Save to Firestore
                try:
                    self.storage.save_place(search_result)
                except Exception as e:
                    logger.error(f"Error saving place to Firestore: {str(e)}")
                
                # Add to unique results and seen places
                unique_results[mapbox_id] = search_result
                seen_places.add(place_key)
                logger.debug(f"Mapbox result: {search_result.name} at {search_result.address}")
            
            # Convert dictionary values to list
            results = list(unique_results.values())
            
            logger.debug(f"Total Mapbox results found: {len(results)}")
            return results
            
        except Exception as e:
            logger.error(f"Error in Mapbox search: {str(e)}", exc_info=True)
            return []

    def get_place_details(self, place_id: str) -> SearchResult:
        url = f"{self.base_url}/retrieve/{place_id}"
        response = requests.get(
            url,
            params={"access_token": self.access_token}
        )
        response.raise_for_status()
        data = response.json()
        
        if not data:
            raise ValueError(f"Place with ID {place_id} not found")
            
        feature = data["features"][0] if "features" in data else data
        return SearchResult(
            name=feature.get("name", ""),
            address=feature.get("full_address", ""),
            latitude=feature.get("coordinates", {}).get("latitude", 0.0),
            longitude=feature.get("coordinates", {}).get("longitude", 0.0),
            place_id=feature.get("mapbox_id"),
            source="mapbox"
        ) 
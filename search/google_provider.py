import logging
import googlemaps
from typing import List, Dict, Any, Optional

from search.base import SearchProvider, SearchResult
from search.storage import PlaceStorage
from search.cache import PlacesCache

logger = logging.getLogger(__name__)

class GooglePlacesSearchProvider(SearchProvider):
    def __init__(self, api_key: str):
        self.client = googlemaps.Client(key=api_key)
        self.cache = PlacesCache()
        self.storage = PlaceStorage()
        
    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        # Check cache first
        cached_results = self.cache.get(query, latitude, longitude)
        if cached_results is not None:
            logger.debug("Returning cached results for query: %s", query)
            return cached_results[:limit]
            
        # Get a session token for this search session
        session_token = self.cache.get_session_token()
        
        try:
            # Use Places Autocomplete API with correct parameter names
            response = self.client.places_autocomplete(
                input_text=query,  # Correct parameter name
                language="en",
                types=["establishment"],
                session_token=session_token
            )
            
            results = []
            for prediction in response[:limit]:
                # Get place details for each prediction
                place_id = prediction.get("place_id")
                if place_id:
                    place_details = self.client.place(
                        place_id,
                        fields=["name", "formatted_address", "geometry", "place_id"],
                        session_token=session_token
                    )
                    
                    if "result" in place_details:
                        place = place_details["result"]
                        search_result = SearchResult(
                            name=place.get("name", ""),
                            address=place.get("formatted_address", ""),
                            latitude=place["geometry"]["location"]["lat"],
                            longitude=place["geometry"]["location"]["lng"],
                            place_id=place.get("place_id"),
                            source="google"
                        )
                        
                        # Save to Firestore
                        try:
                            self.storage.save_place(search_result)
                        except Exception as e:
                            logger.error(f"Error saving place to Firestore: {str(e)}")
                            
                        results.append(search_result)
            
            # Cache the results
            self.cache.set(query, latitude, longitude, results)
            return results
            
        except Exception as e:
            logger.error(f"Error in Google Places search: {str(e)}")
            return []

    def get_place_details(self, place_id: str) -> SearchResult:
        try:
            place_details = self.client.place(
                place_id,
                fields=[
                    "name",
                    "formatted_address",
                    "geometry",
                    "place_id",
                    "type",
                    "rating",
                    "formatted_phone_number",
                    "opening_hours",
                    "price_level",
                    "website",
                    "business_status",
                    "address_component"
                ]
            )
            
            if "result" not in place_details:
                raise ValueError(f"Place with ID {place_id} not found")
                
            place = place_details["result"]
            
            # Extract city from address_components
            city = ""
            address_components = place.get("address_components", [])
            for component in address_components:
                if "locality" in component["types"]:
                    city = component["long_name"]
                    break
                elif "administrative_area_level_2" in component["types"] and not city:
                    city = component["long_name"]  # Fallback if locality is not present

            # Add city to the place data for additional_data
            if city:
                place["city"] = city

            return SearchResult(
                name=place.get("name", ""),
                address=place.get("formatted_address", ""),
                latitude=place["geometry"]["location"]["lat"],
                longitude=place["geometry"]["location"]["lng"],
                place_id=place.get("place_id"),
                source="google",
                additional_data=place
            )
        except Exception as e:
            logger.error(f"Error getting Google Places details: {str(e)}")
            raise
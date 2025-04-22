import logging
import googlemaps
import uuid
from typing import List, Dict, Any, Optional
from firebase_admin import firestore
import requests

from search.base import SearchProvider, SearchResult
from search.storage import PlaceStorage
from search.cache import PlacesCache
from search.detail_place import DetailPlace

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

    def get_place_details(self, place_id: str) -> DetailPlace:
        try:
            # Use the cached result if available
            cached_details = self.cache.get_details(place_id)
            if cached_details:
                logger.debug(f"Using cached details for place_id: {place_id}")
                return cached_details
                
            # Configure URL and parameters
            url = f"{self.base_url}/place/details/json"
            params = {
                "place_id": place_id,
                "key": self.api_key,
                "fields": "name,place_id,formatted_address,geometry,types,photos,formatted_phone_number,opening_hours,rating,price_level"
            }
            
            # Make the request
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Parse the response
            place_details = response.json()
            
            # Check for errors
            if place_details.get("status") != "OK":
                error = place_details.get("error_message", "Unknown error")
                logger.error(f"Error from Google Places API: {error}")
                raise ValueError(f"Error fetching place details: {error}")
                
            place = place_details["result"]
            
            # Extract location
            location = place.get("geometry", {}).get("location", {})
            latitude = location.get("lat", 0.0)
            longitude = location.get("lng", 0.0)
            coordinate = firestore.GeoPoint(latitude, longitude)
            
            # Extract city from address components
            address_components = place.get("address_components", [])
            city = ""
            for component in address_components:
                if "locality" in component.get("types", []):
                    city = component.get("long_name", "")
                    break
            
            # Create a DetailPlace object with deterministic ID
            detail_place = DetailPlace.create_with_deterministic_id(
                name=place.get("name", ""),
                address=place.get("formatted_address", ""),
                city=city,
                google_places_id=place.get("place_id"),
                coordinate=coordinate,
                categories=place.get("types", []),
                phone=place.get("formatted_phone_number"),
                rating=place.get("rating"),
                open_hours=place.get("opening_hours", {}).get("weekday_text", []),
                description=place.get("formatted_address"),
                price_level=str(place.get("price_level")) if place.get("price_level") is not None else None,
                reservable=None,  # Not provided by Google Places
                serves_breakfast=None,  # Not provided by Google Places
                serves_lunch=None,  # Not provided by Google Places
                serves_dinner=None,  # Not provided by Google Places
                instagram=None,  # Not provided by Google Places
                twitter=None  # Not provided by Google Places
            )
            
            # Cache the result
            self.cache.add_details(place_id, detail_place)
            
            return detail_place
        except Exception as e:
            logger.error(f"Error getting Google Places details: {str(e)}")
            raise
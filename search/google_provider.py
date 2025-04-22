import logging
import googlemaps
import uuid
from typing import List, Dict, Any, Optional
from firebase_admin import firestore

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

            # Create a GeoPoint from the coordinates
            location = place["geometry"]["location"]
            coordinate = firestore.GeoPoint(location["lat"], location["lng"])

            return DetailPlace(
                id=str(uuid.uuid4()).upper(),
                name=place.get("name", ""),
                address=place.get("formatted_address", ""),
                city=city,
                google_places_id=place.get("place_id"),
                coordinate=coordinate,  # Use GeoPoint instead of separate lat/lng
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
        except Exception as e:
            logger.error(f"Error getting Google Places details: {str(e)}")
            raise
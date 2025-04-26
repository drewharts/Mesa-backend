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
            
            # Create a SearchResult to check for duplicates
            search_result = SearchResult(
                name=place.get("name", ""),
                address=place.get("formatted_address", ""),
                latitude=location["lat"],
                longitude=location["lng"],
                place_id=place.get("place_id"),
                source="google"
            )
            
            # Check if this place already exists in our database
            existing_id = self.storage._check_for_duplicate(search_result)
            
            # If we found an existing place, get its details from Firestore
            if existing_id:
                logger.info(f"Found existing place with ID: {existing_id}")
                try:
                    # Get the place from Firestore
                    places_ref = self.storage.db.collection('places')
                    place_doc = places_ref.document(existing_id).get()
                    
                    if place_doc.exists:
                        place_data = place_doc.to_dict()
                        # Create a DetailPlace from the Firestore data
                        return DetailPlace(
                            id=existing_id,  # Use the existing ID
                            name=place_data.get('name', ''),
                            address=place_data.get('address', ''),
                            city=place_data.get('city', ''),
                            mapbox_id=place_data.get('mapboxId'),
                            google_places_id=place_data.get('googlePlacesId'),
                            coordinate=place_data.get('coordinate'),
                            categories=place_data.get('categories', []),
                            phone=place_data.get('phone'),
                            rating=place_data.get('rating'),
                            open_hours=place_data.get('openHours', []),
                            description=place_data.get('description'),
                            price_level=place_data.get('priceLevel'),
                            reservable=place_data.get('reservable'),
                            serves_breakfast=place_data.get('servesBreakfast'),
                            serves_lunch=place_data.get('servesLunch'),
                            serves_dinner=place_data.get('servesDinner'),
                            instagram=place_data.get('instagram'),
                            twitter=place_data.get('twitter')
                        )
                except Exception as e:
                    logger.error(f"Error retrieving existing place from Firestore: {str(e)}")
                    # Continue with creating a new place if there's an error

            # If no existing place found or error retrieving it, create a new one
            # Generate a UUID for the place
            place_uuid = str(uuid.uuid4()).upper()
            
            # First save to Firestore to get the document ID
            places_ref = self.storage.db.collection('places')
            place_data = {
                'id': place_uuid,  # Add the UUID as the id field
                'name': place.get("name", ""),
                'address': place.get("formatted_address", ""),
                'city': city,
                'googlePlacesId': place.get("place_id"),
                'coordinate': coordinate,
                'categories': place.get("types", []),
                'phone': place.get("formatted_phone_number"),
                'rating': place.get("rating"),
                'openHours': place.get("opening_hours", {}).get("weekday_text", []),
                'description': place.get("formatted_address"),
                'priceLevel': str(place.get("price_level")) if place.get("price_level") is not None else None,
                'reservable': None,  # Not provided by Google Places
                'servesBreakfast': None,  # Not provided by Google Places
                'servesLunch': None,  # Not provided by Google Places
                'servesDinner': None,  # Not provided by Google Places
                'instagram': None,  # Not provided by Google Places
                'twitter': None  # Not provided by Google Places
            }
            # Create the document with the specific ID
            doc_ref = places_ref.document(place_uuid)
            doc_ref.set(place_data)

            return DetailPlace(
                id=place_uuid,  # Use the generated UUID
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
        except Exception as e:
            logger.error(f"Error getting Google Places details: {str(e)}")
            raise
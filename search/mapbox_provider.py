import logging
import requests
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from firebase_admin import firestore

from search.base import SearchProvider, SearchResult
from search.storage import PlaceStorage
from search.cache import PlacesCache
from search.detail_place import DetailPlace

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
        
        url = f"{self.base_url}/suggest"
        
        try:
            response = requests.get(url, params=params)
            
            if response.status_code != 200:
                logger.error(f"Mapbox API Error: {response.text}")
                return []
                
            response.raise_for_status()
            data = response.json()
            
            # Use a dictionary to track unique results by mapbox_id and name+address+coordinates combination
            unique_results = {}
            seen_places = set()
            
            for suggestion in data.get("suggestions", []):
                # Get the mapbox_id first to check for duplicates
                mapbox_id = suggestion.get("mapbox_id")
                if not mapbox_id:
                    continue
                
                # Get the name and full address
                name = suggestion.get("name", "")
                full_address = suggestion.get("place_formatted", "")
                
                # Get coordinates if available
                point = suggestion.get("point", {})
                coordinates = point.get("coordinates", [])
                # Mapbox returns coordinates as [longitude, latitude]
                longitude = coordinates[0] if coordinates and len(coordinates) > 0 else 0.0
                latitude = coordinates[1] if coordinates and len(coordinates) > 1 else 0.0
                
                # Create a unique key combining name, address, and coordinates
                place_key = f"{name.lower()}|{full_address.lower()}|{latitude}|{longitude}"
                
                # Skip if we've seen this exact place before (by ID or name+address+coordinates)
                if mapbox_id in unique_results or place_key in seen_places:
                    continue
                
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
            
            # Convert dictionary values to list
            results = list(unique_results.values())
            
            return results
            
        except Exception as e:
            logger.error(f"Error in Mapbox search: {str(e)}", exc_info=True)
            return []

    def get_place_details(self, place_id: str) -> DetailPlace:
        # URL encode the place_id to handle special characters
        encoded_place_id = requests.utils.quote(place_id)
        url = f"{self.base_url}/retrieve/{encoded_place_id}"
        params = {
            "access_token": self.access_token,
            "session_token": self.cache.get_session_token() if hasattr(self, 'cache') else None
        }
        
        # Remove None values from params
        params = {k: v for k, v in params.items() if v is not None}
        
        logger.debug(f"Retrieving place details for ID: {place_id}")
        logger.debug(f"Encoded URL: {url}")
        logger.debug(f"Request params: {params}")
        
        try:
            response = requests.get(url, params=params)
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Response body: {response.text}")
            
            response.raise_for_status()
            data = response.json()
            
            if not data or "features" not in data or not data["features"]:
                raise ValueError(f"Place with ID {place_id} not found")
                
            feature = data["features"][0]
            properties = feature.get("properties", {})
            
            # Mapbox returns coordinates as [longitude, latitude]
            coordinates = feature.get("geometry", {}).get("coordinates", [])
            longitude = coordinates[0] if coordinates and len(coordinates) > 0 else 0.0
            latitude = coordinates[1] if coordinates and len(coordinates) > 1 else 0.0
            
            # Create a GeoPoint from the coordinates
            coordinate = firestore.GeoPoint(latitude, longitude)
            
            # Create a SearchResult to check for duplicates
            search_result = SearchResult(
                name=properties.get("name", ""),
                address=properties.get("full_address", ""),
                latitude=latitude,
                longitude=longitude,
                place_id=place_id,
                source="mapbox"
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
            
            # Extract context information
            context = properties.get("context", {})
            city = context.get("place", {}).get("name", "")
            neighborhood = context.get("neighborhood", {}).get("name", "")
            region = context.get("region", {}).get("name", "")
            country = context.get("country", {}).get("name", "")
            postal_code = context.get("postcode", {}).get("name", "")
            
            # Extract additional metadata
            metadata = properties.get("metadata", {})
            wheelchair_accessible = metadata.get("wheelchair_accessible", False)
            
            # Extract operational status
            operational_status = properties.get("operational_status", "")
            
            # Extract POI categories
            poi_categories = properties.get("poi_category", [])
            poi_category_ids = properties.get("poi_category_ids", [])
            
            # Combine all categories
            all_categories = list(set(poi_categories + poi_category_ids))
            
            # Create a more detailed description
            description = f"{properties.get('description', '')}"
            if neighborhood:
                description += f" Located in {neighborhood}."
            
            # If no existing place found or error retrieving it, create a new one
            # Generate a UUID for the place
            place_uuid = str(uuid.uuid4()).upper()
            
            # First save to Firestore to get the document ID
            places_ref = self.storage.db.collection('places')
            place_data = {
                'id': place_uuid,  # Add the UUID as the id field
                'name': properties.get("name", ""),
                'address': properties.get("full_address", ""),
                'city': city,
                'mapboxId': place_id,
                'coordinate': coordinate,
                'categories': all_categories,
                'phone': properties.get("phone"),
                'rating': properties.get("rating"),
                'openHours': properties.get("openHours", []),
                'description': description,
                'priceLevel': properties.get("priceLevel"),
                'reservable': properties.get("reservable"),
                'servesBreakfast': properties.get("servesBreakfast"),
                'servesLunch': properties.get("servesLunch"),
                'servesDinner': properties.get("servesDinner"),
                'instagram': properties.get("instagram"),
                'twitter': properties.get("twitter")
            }
            # Create the document with the specific ID
            doc_ref = places_ref.document(place_uuid)
            doc_ref.set(place_data)

            return DetailPlace(
                id=place_uuid,  # Use the generated UUID
                name=properties.get("name", ""),
                address=properties.get("full_address", ""),
                city=city,
                mapbox_id=place_id,
                coordinate=coordinate,
                categories=all_categories,
                phone=properties.get("phone"),
                rating=properties.get("rating"),
                open_hours=properties.get("openHours", []),
                description=description,
                price_level=properties.get("priceLevel"),
                reservable=properties.get("reservable"),
                serves_breakfast=properties.get("servesBreakfast"),
                serves_lunch=properties.get("servesLunch"),
                serves_dinner=properties.get("servesDinner"),
                instagram=properties.get("instagram"),
                twitter=properties.get("twitter")
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error retrieving place details from Mapbox: {str(e)}")
            raise ValueError(f"Failed to retrieve place details: {str(e)}") 
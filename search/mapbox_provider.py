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
        
        try:
            # Use the cached result if available
            cached_details = self.cache.get_details(place_id)
            if cached_details:
                logger.debug(f"Using cached details for place_id: {place_id}")
                return cached_details
                
            # Construct the URL for the Mapbox Retrieve API
            url = f"https://api.mapbox.com/search/searchbox/v1/retrieve/{encoded_place_id}"
            params = {
                "access_token": self.access_token,
                "language": "en"
            }
            
            # Make the request
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Parse the response
            data = response.json()
            
            if "message" in data:
                logger.error(f"Mapbox API error: {data['message']}")
                raise ValueError(f"Error retrieving place details: {data['message']}")
                
            # Extract relevant data from the feature
            if "features" not in data or not data["features"]:
                raise ValueError("No place found with the given ID")
                
            feature = data['features'][0]
            properties = feature.get('properties', {})
            geometry = feature.get('geometry', {})
            context = properties.get('context', {})
            
            # Extract coordinates
            coordinates = geometry.get('coordinates', [0.0, 0.0])
            # In GeoJSON, coordinates are [longitude, latitude]
            longitude, latitude = coordinates
            coordinate = firestore.GeoPoint(latitude, longitude)
            
            # Extract city information
            city = properties.get('place_formatted', '')
            if not city:
                place_info = context.get('place', {})
                city = place_info.get('name', '')
                
            # If we still don't have a city, try to extract from address
            if not city:
                address_parts = properties.get('full_address', '').split(',')
                if len(address_parts) > 1:
                    city = address_parts[1].strip()
            
            # Extract neighborhood
            neighborhood = context.get('neighborhood', {}).get('name', '')
            region = context.get('region', {}).get('name', '')
            country = context.get('country', {}).get('name', '')
            postal_code = context.get('postcode', {}).get('name', '')
            
            # Extract additional metadata
            metadata = properties.get('metadata', {})
            wheelchair_accessible = metadata.get('wheelchair_accessible', False)
            
            # Extract operational status
            operational_status = properties.get('operational_status', '')
            
            # Extract POI categories
            poi_categories = properties.get('poi_category', [])
            poi_category_ids = properties.get('poi_category_ids', [])
            
            # Combine all categories
            all_categories = list(set(poi_categories + poi_category_ids))
            
            # Create a more detailed description
            description = f"{properties.get('description', '')}"
            if neighborhood:
                description += f" Located in {neighborhood}."
            
            # Create a DetailPlace object with deterministic ID
            detail_place = DetailPlace.create_with_deterministic_id(
                name=properties.get('name', ''),
                address=properties.get('full_address', ''),
                city=city,
                mapbox_id=place_id,
                coordinate=coordinate,
                categories=all_categories,
                phone=properties.get('phone'),
                rating=properties.get('rating'),
                open_hours=properties.get('openHours', []),
                description=description,
                price_level=properties.get('priceLevel'),
                reservable=properties.get('reservable'),
                serves_breakfast=properties.get('servesBreakfast'),
                serves_lunch=properties.get('servesLunch'),
                serves_dinner=properties.get('servesDinner'),
                instagram=properties.get('instagram'),
                twitter=properties.get('twitter')
            )
            
            # Cache the result
            self.cache.add_details(place_id, detail_place)
            
            return detail_place
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error retrieving place details from Mapbox: {str(e)}")
            raise ValueError(f"Failed to retrieve place details: {str(e)}") 
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
            # Retrieve place details from Mapbox
            url = f"https://api.mapbox.com/search/searchbox/v1/retrieve/{encoded_place_id}?access_token={self.access_token}"
            response = requests.get(url)
            
            # Raise an exception for HTTP errors
            response.raise_for_status()
            
            # Parse the response
            data = response.json()
            
            # Check if we have features
            if 'features' not in data or not data['features']:
                raise ValueError(f"No place found for ID: {place_id}")
                
            # Get the first feature
            feature = data['features'][0]
            
            # Extract properties
            properties = feature.get('properties', {})
            
            # Extract coordinates
            geometry = feature.get('geometry', {})
            coordinates = geometry.get('coordinates', [0, 0])
            longitude, latitude = coordinates
            
            # Create a GeoPoint
            coordinate = firestore.GeoPoint(latitude, longitude)
            
            # Extract address components
            context = properties.get('context', {})
            city = context.get('locality', {}).get('name', context.get('place', {}).get('name', ''))
            
            # Extract neighborhood
            neighborhood = context.get('neighborhood', {}).get('name', '')
            
            # Extract address
            full_address = properties.get('full_address', '')
            if not full_address:
                address_parts = []
                
                if properties.get('address', ''):
                    address_parts.append(properties.get('address', ''))
                
                if city:
                    address_parts.append(city)
                
                if context.get('region', {}).get('name', ''):
                    address_parts.append(context.get('region', {}).get('name', ''))
                
                if context.get('country', {}).get('name', ''):
                    address_parts.append(context.get('country', {}).get('name', ''))
                
                if context.get('postcode', {}).get('name', ''):
                    address_parts.append(context.get('postcode', {}).get('name', ''))
                
                full_address = ', '.join([part for part in address_parts if part])
            
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
            
            return DetailPlace(
                id=str(uuid.uuid4()).upper(),
                name=properties.get("name", ""),
                address=properties.get("full_address", ""),
                city=city,
                mapbox_id=place_id,  # Use the original place_id passed to the method
                coordinate=coordinate,  # Use GeoPoint instead of separate lat/lng
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
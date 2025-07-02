import logging
import googlemaps
from typing import Dict, Any, Optional, Tuple
import os

logger = logging.getLogger(__name__)

class GeocodingService:
    """Service for geocoding location names to coordinates and addresses."""
    
    def __init__(self):
        self.google_api_key = os.environ.get('GOOGLE_PLACES_API_KEY')
        self.client = None
        if self.google_api_key:
            self.client = googlemaps.Client(key=self.google_api_key)
    
    def geocode_location(self, location_name: str) -> Optional[Dict[str, Any]]:
        """Convert a location name to coordinates and full address.
        
        Args:
            location_name: Name of the location to geocode
            
        Returns:
            Dict containing:
            - coordinates: Tuple[float, float] (latitude, longitude)
            - formatted_address: str
            - place_id: str (Google Place ID)
            - components: Dict with address components
        """
        if not self.client:
            logger.error("Google Maps client not initialized. Check GOOGLE_PLACES_API_KEY")
            return None
            
        if not location_name or not location_name.strip():
            return None
        
        try:
            # Use Google Geocoding API
            results = self.client.geocode(location_name)
            
            if not results:
                logger.info(f"No geocoding results found for: {location_name}")
                return None
            
            # Use the first result
            result = results[0]
            geometry = result.get('geometry', {})
            location = geometry.get('location', {})
            
            # Extract address components
            components = {}
            for component in result.get('address_components', []):
                types = component.get('types', [])
                if 'locality' in types:
                    components['city'] = component['long_name']
                elif 'administrative_area_level_1' in types:
                    components['state'] = component['long_name']
                elif 'country' in types:
                    components['country'] = component['long_name']
                elif 'postal_code' in types:
                    components['postal_code'] = component['long_name']
            
            return {
                'coordinates': (location.get('lat'), location.get('lng')),
                'formatted_address': result.get('formatted_address', ''),
                'place_id': result.get('place_id', ''),
                'components': components
            }
            
        except Exception as e:
            logger.error(f"Error geocoding location '{location_name}': {str(e)}", exc_info=True)
            return None
    
    def reverse_geocode(self, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
        """Convert coordinates to an address.
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            
        Returns:
            Same format as geocode_location()
        """
        if not self.client:
            logger.error("Google Maps client not initialized. Check GOOGLE_PLACES_API_KEY")
            return None
        
        try:
            results = self.client.reverse_geocode((latitude, longitude))
            
            if not results:
                logger.info(f"No reverse geocoding results found for: ({latitude}, {longitude})")
                return None
            
            # Use the first result
            result = results[0]
            
            # Extract address components
            components = {}
            for component in result.get('address_components', []):
                types = component.get('types', [])
                if 'locality' in types:
                    components['city'] = component['long_name']
                elif 'administrative_area_level_1' in types:
                    components['state'] = component['long_name']
                elif 'country' in types:
                    components['country'] = component['long_name']
                elif 'postal_code' in types:
                    components['postal_code'] = component['long_name']
            
            return {
                'coordinates': (latitude, longitude),
                'formatted_address': result.get('formatted_address', ''),
                'place_id': result.get('place_id', ''),
                'components': components
            }
            
        except Exception as e:
            logger.error(f"Error reverse geocoding ({latitude}, {longitude}): {str(e)}", exc_info=True)
            return None
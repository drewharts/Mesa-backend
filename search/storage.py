import os
import json
import logging
import uuid
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Optional, List
import math

from search.base import SearchResult

logger = logging.getLogger(__name__)

# Custom JSON encoder to handle Firestore GeoPoint objects
class FirestoreEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, firestore.GeoPoint):
            return {
                'latitude': obj.latitude,
                'longitude': obj.longitude
            }
        return super().default(obj)

class PlaceStorage:
    def __init__(self):
        # Initialize Firestore if not already initialized
        if not firebase_admin._apps:
            try:
                # Get Firebase credentials from environment variable
                firebase_creds = os.getenv('FIREBASE_CREDENTIALS')
                if not firebase_creds:
                    logger.warning("FIREBASE_CREDENTIALS environment variable not found")
                    self.db = None
                    return
                
                try:
                    # Parse the JSON string from environment variable
                    cred_dict = json.loads(firebase_creds)
                    
                    # Create a temporary credentials file
                    temp_cred_path = 'temp_credentials.json'
                    with open(temp_cred_path, 'w') as f:
                        json.dump(cred_dict, f)
                    
                    # Initialize Firebase with the temporary file
                    cred = credentials.Certificate(temp_cred_path)
                    firebase_admin.initialize_app(cred)
                    
                    # Remove the temporary file
                    os.remove(temp_cred_path)
                    
                    self.db = firestore.client()
                    logger.info("Firebase initialized successfully")
                except json.JSONDecodeError:
                    logger.error("Failed to parse Firebase credentials JSON")
                    self.db = None
                except Exception as e:
                    logger.error(f"Failed to initialize Firebase: {str(e)}")
                    self.db = None
            except Exception as e:
                logger.error(f"Error in Firebase initialization: {str(e)}")
                self.db = None
        else:
            try:
                self.db = firestore.client()
                logger.info("Using existing Firebase instance")
            except Exception as e:
                logger.error(f"Error getting Firestore client: {str(e)}")
                self.db = None

    def _save_google_place(self, place: SearchResult) -> str:
        """Save a Google Places result to Firestore."""
        try:
            # Extract Google Places specific data
            additional_data = place.additional_data or {}
            
            # Convert place to dictionary matching DetailPlace structure
            place_data = {
                'id': str(uuid.uuid4()).upper(),  # Format UUID in uppercase with hyphens
                'name': place.name,
                'address': place.address,
                'city': additional_data.get('city', ""),  # Get city from additional_data, default to empty string if None
                'mapboxId': None,  # Google Places don't have Mapbox ID
                'googlePlacesId': place.place_id,  # Store the Google Places specific ID
                'coordinate': firestore.GeoPoint(place.latitude, place.longitude),
                'categories': additional_data.get('types'),  # Google Places uses 'types' for categories
                'phone': additional_data.get('formatted_phone_number'),
                'rating': additional_data.get('rating'),
                'openHours': additional_data.get('opening_hours', {}).get('weekday_text'),
                'description': additional_data.get('formatted_address'),
                'priceLevel': str(additional_data.get('price_level')) if additional_data.get('price_level') is not None else None,
                'reservable': additional_data.get('reservable'),
                'servesBreakfast': None,  # Not provided by Google Places
                'servesLunch': None,     # Not provided by Google Places
                'servesDinner': None,    # Not provided by Google Places
                'instagram': None,        # Not provided by Google Places
                'twitter': None           # Not provided by Google Places
            }
            
            # Save to Firestore
            if hasattr(self, 'db'):
                places_ref = self.db.collection('places')
                doc_ref = places_ref.add(place_data)
                return doc_ref[1].id
            else:
                return place_data['id']
                
        except Exception as e:
            logger.error(f"Error processing Google Place: {str(e)}")
            return f"dummy_id_{place.place_id}"

    def _save_mapbox_place(self, place: SearchResult) -> str:
        """Save a Mapbox result to Firestore."""
        try:
            # Extract Mapbox specific data
            additional_data = place.additional_data or {}
            
            # Convert place to dictionary matching DetailPlace structure
            place_data = {
                'id': str(uuid.uuid4()).upper(),  # Format UUID in uppercase with hyphens
                'name': place.name,
                'address': place.address,
                'city': additional_data.get('city'),
                'mapboxId': place.place_id,  # Mapbox places have Mapbox ID
                'googlePlacesId': None,  # Mapbox places don't have Google Places ID
                'coordinate': firestore.GeoPoint(place.latitude, place.longitude),
                'categories': additional_data.get('categories'),
                'phone': additional_data.get('phone'),
                'rating': additional_data.get('rating'),
                'openHours': additional_data.get('openHours'),
                'description': additional_data.get('description'),
                'priceLevel': additional_data.get('priceLevel'),
                'reservable': additional_data.get('reservable'),
                'servesBreakfast': additional_data.get('servesBreakfast'),
                'servesLunch': additional_data.get('servesLunch'),
                'servesDinner': additional_data.get('servesDinner'),
                'instagram': additional_data.get('instagram'),
                'twitter': additional_data.get('twitter')
            }
            
            # Save to Firestore
            if hasattr(self, 'db'):
                places_ref = self.db.collection('places')
                doc_ref = places_ref.add(place_data)
                return doc_ref[1].id
            else:
                return place_data['id']
            
        except Exception as e:
            logger.error(f"Error processing Mapbox Place: {str(e)}")
            return f"dummy_id_{place.place_id}"
        
    def _normalize_string(self, s: str) -> str:
        """Normalize a string for comparison by removing extra spaces and converting to lowercase."""
        if not s:
            return ""
        return " ".join(s.lower().split())

    def _check_for_duplicate(self, place: SearchResult) -> Optional[str]:
        """Check if a place already exists in the database.
        Returns the existing place's ID if found, None otherwise."""
        try:
            if not hasattr(self, 'db'):
                return None
                
            places_ref = self.db.collection('places')
            
            # First check by place_id if available
            if place.place_id:
                # Check for Google Places ID
                if place.source in ['google', 'google_places']:
                    existing_places = places_ref.where('googlePlacesId', '==', place.place_id).get()
                    if existing_places:
                        return existing_places[0].id
                
                # Check for Mapbox ID
                elif place.source == 'mapbox':
                    existing_places = places_ref.where('mapboxId', '==', place.place_id).get()
                    if existing_places:
                        return existing_places[0].id
            
            # If no match by ID, check by name and proximity
            normalized_name = self._normalize_string(place.name)
            
            # Get all places with the same name
            places_with_same_name = places_ref.where('name', '==', place.name).get()
            
            # Check each place with the same name for proximity
            for doc in places_with_same_name:
                doc_data = doc.to_dict()
                doc_coordinate = doc_data.get('coordinate')
                
                if doc_coordinate:
                    # Calculate distance between coordinates (in feet)
                    # Using the Haversine formula to calculate distance between two points on Earth
                    lat1, lon1 = place.latitude, place.longitude
                    lat2, lon2 = doc_coordinate.latitude, doc_coordinate.longitude
                    
                    # Convert to radians
                    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
                    
                    # Haversine formula
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
                    c = 2 * math.asin(math.sqrt(a))
                    r = 20902231  # Radius of earth in feet
                    distance = c * r
                    
                    # If within 100 feet, it's a duplicate
                    if distance <= 100:
                        logger.info(f"Found duplicate place by name and proximity: {place.name}")
                        return doc.id
            
            # No match found
            return None
            
        except Exception as e:
            logger.error(f"Error checking for duplicates: {str(e)}")
            return None

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in meters using Haversine formula"""
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of Earth in meters
        r = 6371000
        
        return c * r

    def find_nearby_places(self, latitude: float, longitude: float, radius_meters: int = 50, limit: int = 20) -> List[SearchResult]:
        """Find places within the specified radius of the given coordinates"""
        try:
            places_ref = self.db.collection('places')
            
            # Get all places (we'll filter by distance since Firestore geo queries are complex)
            # For better performance in production, consider using Firestore geo queries or a spatial index
            all_places = places_ref.limit(1000).get()  # Limit to prevent excessive reads
            
            nearby_places = []
            
            for doc in all_places:
                place_data = doc.to_dict()
                coordinate = place_data.get('coordinate')
                
                if coordinate:
                    place_lat = coordinate.latitude
                    place_lng = coordinate.longitude
                    
                    # Calculate distance
                    distance = self._calculate_distance(latitude, longitude, place_lat, place_lng)
                    
                    if distance <= radius_meters:
                        # Convert back to SearchResult
                        search_result = SearchResult(
                            name=place_data.get('name', ''),
                            address=place_data.get('address', ''),
                            latitude=place_lat,
                            longitude=place_lng,
                            place_id=doc.id,  # Use Firestore document ID for consistency
                            source=place_data.get('source', 'firestore'),
                            additional_data={
                                'firestore_id': doc.id,
                                'distance_meters': round(distance, 2),
                                'googlePlacesId': place_data.get('googlePlacesId'),
                                'mapboxId': place_data.get('mapboxId'),
                                **{k: v for k, v in place_data.items() if k not in ['name', 'address', 'coordinate', 'place_id', 'source', 'googlePlacesId', 'mapboxId']}
                            }
                        )
                        nearby_places.append(search_result)
            
            # Sort by distance and limit results
            nearby_places.sort(key=lambda x: x.additional_data.get('distance_meters', 0))
            return nearby_places[:limit]
            
        except Exception as e:
            logger.error(f"Error finding nearby places in Firestore: {str(e)}")
            return []

    def save_place(self, place: SearchResult) -> str:
        """Save a place to Firestore and return its ID."""
        try:
            # Check if place already exists
            places_ref = self.db.collection('places')
            existing_places = places_ref.where('place_id', '==', place.place_id).get()
            
            if existing_places:
                # Place already exists, return its ID
                return existing_places[0].id
                
            # Create new place document
            place_data = {
                'name': place.name,
                'address': place.address,
                'coordinate': firestore.GeoPoint(place.latitude, place.longitude),
                'place_id': place.place_id,
                'source': place.source,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            # Add any additional data
            if place.additional_data:
                # Filter out internal fields that shouldn't be stored
                filtered_data = {k: v for k, v in place.additional_data.items() 
                               if k not in ['firestore_id', 'distance_meters']}
                place_data.update(filtered_data)
                
            # Save to Firestore
            doc_ref = places_ref.add(place_data)
            return doc_ref[1].id  # Return the document ID
            
        except Exception as e:
            logger.error(f"Error saving place to Firestore: {str(e)}")
            return f"error_{place.place_id}"

    def save_place_old(self, place: SearchResult) -> str:
        """Save a place to Firestore based on its source."""
        try:
            # Check for existing place first
            existing_id = self._check_for_duplicate(place)
            if existing_id:
                return existing_id
                
            if place.source in ['google', 'google_places']:
                place_id = self._save_google_place(place)
                return place_id
            elif place.source == 'mapbox':
                place_id = self._save_mapbox_place(place)
                return place_id
            else:
                logger.warning(f"Unknown source: {place.source}, skipping save")
                return f"dummy_id_{place.place_id}"
        except Exception as e:
            logger.error(f"Error saving place: {str(e)}")
            return f"dummy_id_{place.place_id}" 
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
                    existing_places = places_ref.where('google_place_id', '==', place.place_id).get()
                    if existing_places:
                        # Always return uppercase ID for consistency
                        return existing_places[0].id.upper() if existing_places[0].id else existing_places[0].id
                
                # Check for Mapbox ID
                elif place.source == 'mapbox':
                    existing_places = places_ref.where('mapbox_id', '==', place.place_id).get()
                    if existing_places:
                        # Always return uppercase ID for consistency
                        return existing_places[0].id.upper() if existing_places[0].id else existing_places[0].id
            
            # If no match by ID, check by name and proximity
            normalized_name = self._normalize_string(place.name)
            
            # Get all places with the same name
            places_with_same_name = places_ref.where('name', '==', place.name).get()
            
            # Check each place with the same name for proximity
            for doc in places_with_same_name:
                doc_data = doc.to_dict()
                
                # Handle both new and old coordinate formats
                coordinates = doc_data.get('coordinates')
                if coordinates and isinstance(coordinates, dict):
                    lat2, lon2 = coordinates.get('latitude', 0), coordinates.get('longitude', 0)
                else:
                    doc_coordinate = doc_data.get('coordinate')
                    if doc_coordinate and hasattr(doc_coordinate, 'latitude'):
                        lat2, lon2 = doc_coordinate.latitude, doc_coordinate.longitude
                    else:
                        continue
                
                # Calculate distance between coordinates (in feet)
                lat1, lon1 = place.latitude, place.longitude
                
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
                    # Always return uppercase ID for consistency
                    return doc.id.upper() if doc.id else doc.id
            
            # No match found
            return None
            
        except Exception as e:
            logger.error(f"Error checking for duplicates: {str(e)}")
            return None

    def check_for_existing_place_by_tiktok_url(self, tiktok_url: str) -> Optional[str]:
        """Check if a place already exists with the given TikTok URL.
        Returns the existing place's ID if found, None otherwise."""
        try:
            if not hasattr(self, 'db') or not self.db:
                return None
                
            places_ref = self.db.collection('places')
            
            # Get all places that have tiktok_videos
            places_with_videos = places_ref.where('tiktok_videos', '>', []).get()
            
            for doc in places_with_videos:
                place_data = doc.to_dict()
                tiktok_videos = place_data.get('tiktok_videos', [])
                
                # Check if any video has the same URL
                for video in tiktok_videos:
                    if video.get('url') == tiktok_url:
                        logger.info(f"Found existing place {doc.id} with TikTok URL: {tiktok_url}")
                        # Always return uppercase ID for consistency
                        return doc.id.upper() if doc.id else doc.id
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking for existing TikTok URL: {str(e)}")
            return None

    def check_for_existing_place_by_name_and_location(self, name: str, latitude: float, longitude: float) -> Optional[str]:
        """Check if a place already exists with similar name and location.
        Returns the existing place's ID if found, None otherwise."""
        try:
            if not hasattr(self, 'db') or not self.db:
                return None
                
            places_ref = self.db.collection('places')
            
            # Normalize the search name
            normalized_search_name = self._normalize_string(name)
            
            # Get all places and check for similar names and proximity
            # Note: In production, consider using a more efficient query
            all_places = places_ref.limit(1000).get()
            
            for doc in all_places:
                place_data = doc.to_dict()
                place_name = place_data.get('name', '')
                normalized_place_name = self._normalize_string(place_name)
                
                # Check for similar names (exact match or contains)
                name_match = (normalized_search_name == normalized_place_name or 
                             normalized_search_name in normalized_place_name or
                             normalized_place_name in normalized_search_name)
                
                if name_match:
                    # Check proximity
                    coordinates = place_data.get('coordinates')
                    if coordinates and isinstance(coordinates, dict):
                        place_lat = coordinates.get('latitude', 0)
                        place_lon = coordinates.get('longitude', 0)
                    else:
                        doc_coordinate = place_data.get('coordinate')
                        if doc_coordinate and hasattr(doc_coordinate, 'latitude'):
                            place_lat = doc_coordinate.latitude
                            place_lon = doc_coordinate.longitude
                        else:
                            continue
                    
                    # Calculate distance
                    distance = self._calculate_distance(latitude, longitude, place_lat, place_lon)
                    
                    # If within 500 meters (broader than the 100 feet used elsewhere)
                    if distance <= 500:
                        logger.info(f"Found existing place by name similarity and proximity: {place_name}")
                        # Always return uppercase ID for consistency
                        return doc.id.upper() if doc.id else doc.id
            
            return None
            
        except Exception as e:
            logger.error(f"Error checking for existing place by name and location: {str(e)}")
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

    def save_place_with_tiktok_data(self, place: SearchResult, tiktok_videos: list = None) -> str:
        """Save a place to Firestore using the correct format with TikTok video support.
        
        Args:
            place: SearchResult object with place data
            tiktok_videos: List of TikTok video objects (optional)
            
        Returns:
            str: Document ID of the saved place or None on error
        """
        try:
            if not hasattr(self, 'db') or not self.db:
                logger.error("Firestore database not initialized")
                return None
                
            # Check for duplicates first
            existing_id = self._check_for_duplicate(place)
            if existing_id:
                # If place exists and we have TikTok videos, append them
                if tiktok_videos:
                    self._append_tiktok_videos_to_place(existing_id, tiktok_videos)
                return existing_id
            
            # Generate UUID for the place - MUST BE UPPERCASE
            place_uuid = str(uuid.uuid4()).upper()
            
            # Extract additional data
            additional_data = place.additional_data or {}
            
            # Build place data in the correct format
            place_data = {
                'id': place_uuid,
                'name': place.name,
                'address': place.address,
                'city': additional_data.get('city', ''),
                'coordinates': {
                    'latitude': place.latitude,
                    'longitude': place.longitude
                },
                'categories': additional_data.get('categories', []) or additional_data.get('types', []),
                'created_at': firestore.SERVER_TIMESTAMP,
                'source': place.source
            }
            
            # Add source-specific IDs
            if place.source in ['google', 'google_places']:
                place_data['google_place_id'] = place.place_id
            elif place.source == 'mapbox':
                place_data['mapbox_id'] = place.place_id
            
            # Add TikTok videos if provided
            if tiktok_videos:
                place_data['tiktok_videos'] = tiktok_videos
            
            # Add other optional fields
            if additional_data.get('phone'):
                place_data['phone'] = additional_data['phone']
            if additional_data.get('rating'):
                place_data['rating'] = additional_data['rating']
            if additional_data.get('description'):
                place_data['description'] = additional_data['description']
                
            # Save to Firestore using the UUID as document ID
            places_ref = self.db.collection('places')
            doc_ref = places_ref.document(place_uuid)
            doc_ref.set(place_data)
            
            logger.info(f"Saved place {place.name} with ID {place_uuid}")
            return place_uuid
            
        except Exception as e:
            logger.error(f"Error saving place with TikTok data: {str(e)}")
            return None

    def _append_tiktok_videos_to_place(self, place_id: str, tiktok_videos: list):
        """Append TikTok videos to an existing place."""
        try:
            place_ref = self.db.collection('places').document(place_id)
            place_doc = place_ref.get()
            
            if place_doc.exists:
                place_data = place_doc.to_dict()
                existing_videos = place_data.get('tiktok_videos', [])
                
                # Get existing video IDs to avoid duplicates
                existing_video_ids = {video.get('video_id') for video in existing_videos}
                
                # Add new videos that don't already exist
                new_videos = [video for video in tiktok_videos 
                             if video.get('video_id') not in existing_video_ids]
                
                if new_videos:
                    updated_videos = existing_videos + new_videos
                    place_ref.update({'tiktok_videos': updated_videos})
                    logger.info(f"Added {len(new_videos)} new TikTok videos to place {place_id}")
                
        except Exception as e:
            logger.error(f"Error appending TikTok videos to place: {str(e)}")

    def add_place_to_user_external_places(self, user_id: str, place: SearchResult, tiktok_videos: list = None) -> tuple:
        """Add a place to a user's externalPlaces subcollection and save to main places collection.
        
        Args:
            user_id: User ID
            place: SearchResult object
            tiktok_videos: Optional list of TikTok video data
            
        Returns:
            tuple: (place_id, external_place_doc_id) or (None, None) on error
        """
        try:
            if not hasattr(self, 'db') or not self.db:
                logger.error("Firestore database not initialized")
                return None, None
                
            # Save place using the correct format
            place_doc_id = self.save_place_with_tiktok_data(place, tiktok_videos)
            
            if not place_doc_id:
                logger.error("Failed to save place to main collection")
                return None, None
            
            # Add to user's externalPlaces subcollection
            user_ref = self.db.collection('users').document(user_id)
            external_places_ref = user_ref.collection('externalPlaces')
            
            # Create the external place document with minimal reference data
            external_place_data = {
                'placeId': place_doc_id,  # Reference to the main places collection document
                'name': place.name,
                'address': place.address,
                'coordinates': {
                    'latitude': place.latitude,
                    'longitude': place.longitude
                },
                'source': place.source,
                'addedAt': firestore.SERVER_TIMESTAMP
            }
            
            # Check if place already exists in user's external places
            existing_external = external_places_ref.where('placeId', '==', place_doc_id).get()
            if existing_external:
                logger.info(f"Place {place_doc_id} already exists in user {user_id}'s externalPlaces")
                return place_doc_id, existing_external[0].id
            
            # Add to externalPlaces
            doc_ref = external_places_ref.add(external_place_data)
            external_doc_id = doc_ref[1].id
            logger.info(f"Added place {place_doc_id} to user {user_id}'s externalPlaces")
            
            return place_doc_id, external_doc_id
            
        except Exception as e:
            logger.error(f"Error adding place to user's externalPlaces: {str(e)}")
            return None, None

    def trigger_whoosh_reindex(self):
        """Trigger a Whoosh index rebuild to include new places.
        
        Note: This requires the Whoosh provider to be initialized and available.
        In a production environment, consider using a background task queue.
        """
        try:
            from search.whoosh_provider import WhooshSearchProvider
            
            # Create a new Whoosh provider instance
            whoosh_provider = WhooshSearchProvider()
            
            # Clear and rebuild the index
            whoosh_provider.clear_index()
            logger.info("Whoosh index cleared")
            
            # Get all places from Firestore and index them
            if hasattr(self, 'db') and self.db:
                places_ref = self.db.collection('places')
                places = places_ref.get()
                
                # Index each place
                with whoosh_provider.ix.writer() as writer:
                    for place_doc in places:
                        place_data = place_doc.to_dict()
                        
                        # Extract coordinates (handle both new and old formats)
                        coordinates = place_data.get('coordinates')
                        if coordinates and isinstance(coordinates, dict):
                            # New format: {"latitude": x, "longitude": y}
                            latitude = coordinates.get('latitude', 0.0)
                            longitude = coordinates.get('longitude', 0.0)
                        else:
                            # Old format: firestore.GeoPoint
                            coordinate = place_data.get('coordinate')
                            if coordinate and hasattr(coordinate, 'latitude'):
                                latitude = coordinate.latitude
                                longitude = coordinate.longitude
                            else:
                                latitude = longitude = 0.0
                        
                        # Add to Whoosh index with correct structure
                        # IMPORTANT: Ensure place_id is uppercase for consistency
                        writer.add_document(
                            name=place_data.get('name', ''),
                            place_id=place_doc.id.upper() if place_doc.id else place_doc.id,  # Ensure uppercase
                            address=place_data.get('address', ''),
                            latitude=latitude,
                            longitude=longitude
                        )
                
                logger.info(f"Indexed {len(places)} places in Whoosh")
                
                # Force refresh the index
                whoosh_provider.force_refresh()
                return True
            else:
                logger.error("Firestore database not available for reindexing")
                return False
                
        except ImportError:
            logger.error("WhooshSearchProvider not available, trying subprocess method")
            # Fallback to subprocess method
            import subprocess
            import os
            
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            index_script = os.path.join(project_root, 'index_places.py')
            
            result = subprocess.run(['python', index_script], 
                                  capture_output=True, text=True, cwd=project_root)
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Error triggering Whoosh reindex: {str(e)}")
            return False 
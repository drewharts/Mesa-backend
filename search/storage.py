import os
import json
import logging
import uuid
import firebase_admin
from firebase_admin import credentials, firestore
from typing import Optional

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
            
            # If no match by ID, check by name and address
            normalized_name = self._normalize_string(place.name)
            normalized_address = self._normalize_string(place.address)
            
            # Get all places with the same name
            places_with_same_name = places_ref.where('name', '==', place.name).get()
            
            # Check each place with the same name for matching address
            for doc in places_with_same_name:
                doc_data = doc.to_dict()
                doc_address = self._normalize_string(doc_data.get('address', ''))
                
                # If both name and address match, it's a duplicate
                if doc_address == normalized_address:
                    logger.info(f"Found duplicate place by name and address: {place.name}")
                    return doc.id
            
            # No match found
            return None
            
        except Exception as e:
            logger.error(f"Error checking for duplicates: {str(e)}")
            return None

    def save_place(self, place: SearchResult) -> str:
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
        
        # # Check if place already exists
        # places_ref = self.db.collection('places')
        # existing_places = places_ref.where('place_id', '==', place.place_id).get()
        
        # if existing_places:
        #     # Place already exists, return its ID
        #     return existing_places[0].id
            
        # # Create new place document
        # place_data = {
        #     'name': place.name,
        #     'address': place.address,
        #     'coordinate': firestore.GeoPoint(place.latitude, place.longitude),
        #     'place_id': place.place_id,
        #     'source': place.source,
        #     'created_at': firestore.SERVER_TIMESTAMP,
        #     'updated_at': firestore.SERVER_TIMESTAMP
        # }
        
        # # Add any additional data
        # if place.additional_data:
        #     place_data.update(place.additional_data)
            
        # # Save to Firestore
        # doc_ref = places_ref.add(place_data)
        # return doc_ref[1].id 
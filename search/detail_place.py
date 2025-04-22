import uuid
from typing import List, Dict, Any, Optional
from firebase_admin import firestore

from search.search_result import SearchResult

class DetailPlace:
    def __init__(self, 
                 id: str,
                 name: str,
                 address: str,
                 city: str = "",
                 mapbox_id: str = None,
                 google_places_id: str = None,
                 coordinate: firestore.GeoPoint = None,
                 categories: list = None,
                 phone: str = None,
                 rating: float = None,
                 open_hours: list = None,
                 description: str = None,
                 price_level: str = None,
                 reservable: bool = None,
                 serves_breakfast: bool = None,
                 serves_lunch: bool = None,
                 serves_dinner: bool = None,
                 instagram: str = None,
                 twitter: str = None):
        self.id = id
        self.name = name
        self.address = address
        self.city = city
        self.mapbox_id = mapbox_id
        self.google_places_id = google_places_id
        self.coordinate = coordinate or firestore.GeoPoint(0.0, 0.0)
        self.categories = categories or []
        self.phone = phone
        self.rating = rating
        self.open_hours = open_hours or []
        self.description = description
        self.price_level = price_level
        self.reservable = reservable
        self.serves_breakfast = serves_breakfast
        self.serves_lunch = serves_lunch
        self.serves_dinner = serves_dinner
        self.instagram = instagram
        self.twitter = twitter

    @classmethod
    def from_search_result(cls, search_result: SearchResult, source: str = None) -> 'DetailPlace':
        """Create a DetailPlace from a SearchResult."""
        additional_data = search_result.additional_data or {}
        
        return cls(
            id=str(uuid.uuid4()).upper(),
            name=search_result.name,
            address=search_result.address,
            city=additional_data.get('city', ""),
            mapbox_id=search_result.place_id if source == 'mapbox' else None,
            google_places_id=search_result.place_id if source == 'google' else None,
            coordinate=firestore.GeoPoint(search_result.latitude, search_result.longitude),
            categories=additional_data.get('categories', []) or additional_data.get('types', []),
            phone=additional_data.get('phone') or additional_data.get('formatted_phone_number'),
            rating=additional_data.get('rating'),
            open_hours=additional_data.get('openHours', []) or additional_data.get('opening_hours', {}).get('weekday_text', []),
            description=additional_data.get('description') or additional_data.get('formatted_address'),
            price_level=additional_data.get('priceLevel') or str(additional_data.get('price_level')) if additional_data.get('price_level') is not None else None,
            reservable=additional_data.get('reservable'),
            serves_breakfast=additional_data.get('servesBreakfast'),
            serves_lunch=additional_data.get('servesLunch'),
            serves_dinner=additional_data.get('servesDinner'),
            instagram=additional_data.get('instagram'),
            twitter=additional_data.get('twitter')
        )

    def to_firestore_dict(self) -> dict:
        """Convert the DetailPlace to a dictionary format for Firestore."""
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'city': self.city,
            'mapboxId': self.mapbox_id,
            'googlePlacesId': self.google_places_id,
            'coordinate': self.coordinate,
            'categories': self.categories,
            'phone': self.phone,
            'rating': self.rating,
            'openHours': self.open_hours,
            'description': self.description,
            'priceLevel': self.price_level,
            'reservable': self.reservable,
            'servesBreakfast': self.serves_breakfast,
            'servesLunch': self.serves_lunch,
            'servesDinner': self.serves_dinner,
            'instagram': self.instagram,
            'twitter': self.twitter
        }

    def to_dict(self) -> dict:
        """Convert the DetailPlace to a regular dictionary (for API responses)."""
        return {
            'id': self.id,
            'name': self.name,
            'address': self.address,
            'city': self.city,
            'mapboxId': self.mapbox_id,
            'googlePlacesId': self.google_places_id,
            'location': {
                'latitude': self.coordinate.latitude,
                'longitude': self.coordinate.longitude
            },
            'categories': self.categories,
            'phone': self.phone,
            'rating': self.rating,
            'openHours': self.open_hours,
            'description': self.description,
            'priceLevel': self.price_level,
            'reservable': self.reservable,
            'servesBreakfast': self.serves_breakfast,
            'servesLunch': self.serves_lunch,
            'servesDinner': self.serves_dinner,
            'instagram': self.instagram,
            'twitter': self.twitter
        }

    @staticmethod
    def create_with_deterministic_id(name: str, 
                                  address: str, 
                                  city: str = "",
                                  mapbox_id: str = None,
                                  google_places_id: str = None,
                                  coordinate: firestore.GeoPoint = None,
                                  categories: list = None,
                                  phone: str = None,
                                  rating: float = None,
                                  open_hours: list = None,
                                  description: str = None,
                                  price_level: str = None,
                                  reservable: bool = None,
                                  serves_breakfast: bool = None,
                                  serves_lunch: bool = None,
                                  serves_dinner: bool = None,
                                  instagram: str = None,
                                  twitter: str = None) -> 'DetailPlace':
        """Create a DetailPlace with a deterministic ID based on its source-specific ID."""
        # Use the provider-specific ID if available, otherwise generate a random UUID
        if google_places_id:
            # Create a deterministic ID based on Google Places ID
            id_base = f"google_{google_places_id}"
        elif mapbox_id:
            # Create a deterministic ID based on Mapbox ID
            id_base = f"mapbox_{mapbox_id}"
        else:
            # Fallback to random UUID
            id_base = str(uuid.uuid4())
            
        # Create a UUID based on the ID base - this ensures the same place always gets the same ID
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, id_base)).upper()
        
        return DetailPlace(
            id=deterministic_id,
            name=name,
            address=address,
            city=city,
            mapbox_id=mapbox_id,
            google_places_id=google_places_id,
            coordinate=coordinate,
            categories=categories,
            phone=phone,
            rating=rating,
            open_hours=open_hours,
            description=description,
            price_level=price_level,
            reservable=reservable,
            serves_breakfast=serves_breakfast,
            serves_lunch=serves_lunch,
            serves_dinner=serves_dinner,
            instagram=instagram,
            twitter=twitter
        ) 
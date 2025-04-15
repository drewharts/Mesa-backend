from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import whoosh.index
import whoosh.fields
import whoosh.qparser
from whoosh.analysis import StandardAnalyzer
import os
import requests
import googlemaps
from datetime import datetime, timedelta
import logging
import time
import firebase_admin
from firebase_admin import credentials, firestore

logger = logging.getLogger(__name__)

class SearchResult:
    def __init__(self, name: str, address: str, latitude: float, longitude: float, 
                 source: str, place_id: str = None, additional_data: Dict = None):
        self.name = name
        self.address = address
        self.latitude = latitude
        self.longitude = longitude
        self.source = source
        self.place_id = place_id
        self.additional_data = additional_data or {}

class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        pass

class WhooshSearchProvider(SearchProvider):
    def __init__(self, index_path: str = "whoosh_index"):
        self.index_path = index_path
        logger.debug(f"Initializing WhooshSearchProvider with index path: {index_path}")
        self._ensure_index()
        
    def _ensure_index(self):
        if not os.path.exists(self.index_path):
            logger.debug(f"Creating new Whoosh index at {self.index_path}")
            os.mkdir(self.index_path)
            # Simplified schema focusing on name
            schema = whoosh.fields.Schema(
                name=whoosh.fields.TEXT(stored=True, analyzer=StandardAnalyzer()),  # Using StandardAnalyzer for better text matching
                place_id=whoosh.fields.ID(stored=True),
                # Keep these for the response but don't search on them
                address=whoosh.fields.STORED,
                latitude=whoosh.fields.STORED,
                longitude=whoosh.fields.STORED
            )
            whoosh.index.create_in(self.index_path, schema)
        else:
            logger.debug(f"Using existing Whoosh index at {self.index_path}")
        self.ix = whoosh.index.open_dir(self.index_path)

    def search(self, query: str, limit: int = 10) -> List[SearchResult]:
        logger.debug(f"Searching Whoosh index with query: '{query}', limit: {limit}")
        with self.ix.searcher() as searcher:
            # Create a query parser that only searches the name field
            query_parser = whoosh.qparser.QueryParser("name", self.ix.schema)
            q = query_parser.parse(query)
            logger.debug(f"Parsed query: {q}")
            results = searcher.search(q, limit=limit)
            logger.debug(f"Found {len(results)} results in Whoosh index")
            
            search_results = [
                SearchResult(
                    name=result["name"],
                    address=result.get("address", ""),  # Use get() since these are optional
                    latitude=result.get("latitude", 0.0),
                    longitude=result.get("longitude", 0.0),
                    place_id=result["place_id"],
                    source="local_database"
                )
                for result in results
            ]
            
            for result in search_results:
                logger.debug(f"Whoosh result: {result.name} at {result.address}")
            
            return search_results

class MapboxSearchProvider(SearchProvider):
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.mapbox.com/geocoding/v5/mapbox.places"
        self.storage = PlaceStorage()

    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        params = {
            "access_token": self.access_token,
            "q": query,
            "limit": limit,
            "types": "poi",  # Only search for points of interest
        }
        
        # Add proximity if coordinates are provided
        if latitude is not None and longitude is not None:
            params["proximity"] = f"{longitude},{latitude}"
        
        response = requests.get(f"{self.base_url}/{query}.json", params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for feature in data.get("features", []):
            # Only include results that have a name property
            if "text" in feature:
                search_result = SearchResult(
                    name=feature.get("text", ""),
                    address=feature.get("place_name", ""),
                    latitude=feature["center"][1],
                    longitude=feature["center"][0],
                    place_id=feature.get("id"),
                    source="mapbox"
                )
                
                # Save to Firestore
                try:
                    self.storage.save_place(search_result)
                except Exception as e:
                    logger.error(f"Error saving place to Firestore: {str(e)}")
                    
                results.append(search_result)
        return results

class PlacesCache:
    def __init__(self, cache_duration: int = 3600):  # Default cache duration: 1 hour
        self.cache: Dict[str, Tuple[List[SearchResult], datetime]] = {}
        self.cache_duration = cache_duration
        self.session_token = None
        self.session_token_time = None
        
    def _generate_cache_key(self, query: str, latitude: Optional[float], longitude: Optional[float]) -> str:
        """Generate a cache key based on search parameters"""
        loc_str = f"{latitude},{longitude}" if latitude is not None and longitude is not None else "no-loc"
        return f"{query}:{loc_str}"
        
    def get(self, query: str, latitude: Optional[float], longitude: Optional[float]) -> Optional[List[SearchResult]]:
        """Get cached results if they exist and are not expired"""
        cache_key = self._generate_cache_key(query, latitude, longitude)
        if cache_key in self.cache:
            results, timestamp = self.cache[cache_key]
            if datetime.now() - timestamp < timedelta(seconds=self.cache_duration):
                return results
        return None
        
    def set(self, query: str, latitude: Optional[float], longitude: Optional[float], results: List[SearchResult]):
        """Cache the results with current timestamp"""
        cache_key = self._generate_cache_key(query, latitude, longitude)
        self.cache[cache_key] = (results, datetime.now())
        
    def get_session_token(self) -> str:
        """Get or generate a new session token"""
        current_time = time.time()
        if (self.session_token is None or 
            self.session_token_time is None or 
            current_time - self.session_token_time > 300):  # 5 minutes
            self.session_token = str(int(current_time))
            self.session_token_time = current_time
        return self.session_token

class PlaceStorage:
    def __init__(self):
        # Initialize Firestore if not already initialized
        if not firebase_admin._apps:
            cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                   "Firebase Admin SDK Service Account.json")
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()
        
    def save_place(self, place: SearchResult) -> str:
        """Save a place to Firestore and return its ID. Currently a no-op."""
        # For now, just return a dummy ID
        # The actual implementation is kept but commented out for future use
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
        # return doc_ref[1].id  # Return the document ID

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
        
        # Prepare the autocomplete request
        params = {
            "input": query,
            "language": "en",
            "region": "US",
            "types": "establishment",  # Search for businesses/establishments
            "sessiontoken": session_token,
            "fields": "name,formatted_address,geometry,place_id"  # Minimize fields to reduce costs
        }
        
        # Add location bias if coordinates are provided
        if latitude is not None and longitude is not None:
            params["location"] = f"{latitude},{longitude}"
            params["radius"] = 50000  # 50km radius
            
        try:
            # Use Places Autocomplete API
            response = self.client.places_autocomplete(**params)
            
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
                            source="google_places"
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

class SearchOrchestrator:
    def __init__(self, whoosh_provider: WhooshSearchProvider,
                 mapbox_provider: MapboxSearchProvider,
                 google_places_provider: GooglePlacesSearchProvider):
        self.whoosh_provider = whoosh_provider
        self.mapbox_provider = mapbox_provider
        self.google_places_provider = google_places_provider

    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        # Try Whoosh first
        whoosh_results = self.whoosh_provider.search(query, limit)
        
        # If we have 5 or more results from Whoosh, return them
        if len(whoosh_results) >= 5:
            return whoosh_results
            
        # If we have fewer than 5 results, try Mapbox
        mapbox_results = self.mapbox_provider.search(query, limit - len(whoosh_results), latitude, longitude)
        
        # Combine results from both providers
        combined_results = whoosh_results + mapbox_results
        
        # If we still don't have enough results, try Google Places
        if len(combined_results) < 5:
            google_results = self.google_places_provider.search(query, limit - len(combined_results), latitude, longitude)
            combined_results.extend(google_results)
            
        return combined_results

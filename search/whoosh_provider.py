import os
import logging
import whoosh.index
import whoosh.fields
import whoosh.qparser
from whoosh.analysis import StandardAnalyzer
from typing import List, Dict, Any, Optional
import uuid
from firebase_admin import firestore

from search.base import SearchProvider, SearchResult
from search.storage import PlaceStorage
from search.detail_place import DetailPlace

logger = logging.getLogger(__name__)

class WhooshSearchProvider(SearchProvider):
    def __init__(self, index_path: str = "whoosh_index"):
        self.index_path = index_path
        logger.debug(f"Initializing WhooshSearchProvider with index path: {index_path}")
        self._ensure_index()
        self.storage = PlaceStorage()
        
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

    def _is_same_place(self, place1: SearchResult, place2: SearchResult) -> bool:
        """Check if two places are likely the same based on name, address, and coordinates."""
        # Normalize names and addresses for comparison
        name1 = place1.name.lower().strip()
        name2 = place2.name.lower().strip()
        
        # If names are exactly the same
        if name1 == name2:
            # Check if addresses are exactly the same after normalization
            addr1 = place1.address.lower().strip()
            addr2 = place2.address.lower().strip()
            
            # Remove common variations
            for suffix in [', usa', ', united states', ', ut', ', utah']:
                addr1 = addr1.replace(suffix, '')
                addr2 = addr2.replace(suffix, '')
            
            # If addresses are exactly the same after normalization
            if addr1 == addr2:
                # Check if coordinates are very close (within ~100 meters)
                lat_diff = abs(place1.latitude - place2.latitude)
                lon_diff = abs(place1.longitude - place2.longitude)
                if lat_diff < 0.001 and lon_diff < 0.001:  # Approximately 100 meters
                    return True
                
        return False

    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
        with self.ix.searcher() as searcher:
            # Create a query parser that only searches the name field
            query_parser = whoosh.qparser.QueryParser("name", self.ix.schema)
            q = query_parser.parse(query)
            results = searcher.search(q, limit=limit)
            
            # Convert to SearchResult objects with deduplication
            search_results = []
            seen_places = set()
            
            for result in results:
                search_result = SearchResult(
                    name=result["name"],
                    address=result.get("address", ""),  # Use get() since these are optional
                    latitude=result.get("latitude", 0.0),
                    longitude=result.get("longitude", 0.0),
                    place_id=result["place_id"],
                    source="local"
                )
                
                # Create a unique key for this place using name, address, and coordinates
                place_key = f"{search_result.name.lower()}|{search_result.address.lower()}|{search_result.latitude}|{search_result.longitude}"
                
                # Only add if we haven't seen this exact place before
                if place_key not in seen_places:
                    search_results.append(search_result)
                    seen_places.add(place_key)
            
            return search_results

    def get_place_details(self, place_id: str) -> DetailPlace:
        try:
            # Get the place document from Firestore
            places_ref = self.storage.db.collection('places')
            place_doc = places_ref.document(place_id).get()
            
            if not place_doc.exists:
                raise ValueError(f"Place with ID {place_id} not found")
                
            place_data = place_doc.to_dict()
            coordinate = place_data.get('coordinate')
            
            return DetailPlace(
                id=place_id,
                name=place_data.get('name', ''),
                address=place_data.get('address', ''),
                city=place_data.get('city', ''),
                mapbox_id=place_data.get('mapboxId'),
                google_places_id=place_data.get('googlePlacesId'),
                coordinate=coordinate,
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
            logger.error(f"Error getting place from Firestore: {str(e)}")
            raise
            
    def save_place(self, place: SearchResult) -> None:
        with self.ix.writer() as writer:
            writer.add_document(
                name=place.name,
                place_id=place.place_id,
                address=place.address,
                latitude=place.latitude,
                longitude=place.longitude
            )

    def clear_index(self) -> None:
        """Clear all documents from the Whoosh index."""
        logger.info("Clearing Whoosh index")
        with self.ix.writer() as writer:
            writer.delete_by_query(whoosh.qparser.QueryParser("name", self.ix.schema).parse("*"))
        logger.info("Whoosh index cleared successfully") 
import os
import logging
import whoosh.index
import whoosh.fields
import whoosh.qparser
from whoosh.analysis import StandardAnalyzer
from typing import List, Dict, Any, Optional

from search.base import SearchProvider, SearchResult

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

    def search(self, query: str, limit: int = 10, latitude: float = None, longitude: float = None) -> List[SearchResult]:
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
                    source="local"
                )
                for result in results
            ]
            
            for result in search_results:
                logger.debug(f"Whoosh result: {result.name} at {result.address}")
            
            return search_results

    def get_place_details(self, place_id: str) -> SearchResult:
        try:
            # Get the place document from Firestore
            places_ref = self.storage.db.collection('places')
            place_doc = places_ref.document(place_id).get()
            
            if not place_doc.exists:
                raise ValueError(f"Place with ID {place_id} not found")
                
            place_data = place_doc.to_dict()
            coordinate = place_data.get('coordinate')
            
            return SearchResult(
                name=place_data.get('name', ''),
                address=place_data.get('address', ''),
                latitude=coordinate.latitude if coordinate else 0.0,
                longitude=coordinate.longitude if coordinate else 0.0,
                place_id=place_id,
                source='local',
                additional_data=place_data
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
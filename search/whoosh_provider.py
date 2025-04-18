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
                    source="local_database"
                )
                for result in results
            ]
            
            for result in search_results:
                logger.debug(f"Whoosh result: {result.name} at {result.address}")
            
            return search_results

    def get_place_details(self, place_id: str) -> SearchResult:
        with self.ix.searcher() as searcher:
            query = whoosh.qparser.QueryParser("place_id", self.ix.schema).parse(place_id)
            results = searcher.search(query, limit=1)
            
            if not results:
                raise ValueError(f"Place with ID {place_id} not found")
                
            result = results[0]
            return SearchResult(
                name=result["name"],
                address=result.get("address", ""),
                latitude=result.get("latitude", 0.0),
                longitude=result.get("longitude", 0.0),
                place_id=result["place_id"],
                source="local_database"
            )
            
    def save_place(self, place: SearchResult) -> None:
        with self.ix.writer() as writer:
            writer.add_document(
                name=place.name,
                place_id=place.place_id,
                address=place.address,
                latitude=place.latitude,
                longitude=place.longitude
            ) 
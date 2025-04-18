import logging
from dotenv import load_dotenv
import os
from search import WhooshSearchProvider, MapboxSearchProvider, GooglePlacesSearchProvider, SearchOrchestrator

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def test_search():
    """Test the search functionality with all providers."""
    # Initialize search providers
    whoosh_provider = WhooshSearchProvider()
    mapbox_provider = MapboxSearchProvider(access_token=os.getenv('MAPBOX_ACCESS_TOKEN'))
    google_places_provider = GooglePlacesSearchProvider(api_key=os.getenv('GOOGLE_PLACES_API_KEY'))
    
    # Initialize search orchestrator
    search_orchestrator = SearchOrchestrator(
        whoosh_provider=whoosh_provider,
        mapbox_provider=mapbox_provider,
        google_places_provider=google_places_provider
    )
    
    # Test search with a simple query
    query = "coffee"
    logger.info(f"Testing search with query: {query}")
    
    # Test each provider individually
    logger.info("\nTesting Whoosh search:")
    whoosh_results = whoosh_provider.search(query, limit=3)
    logger.info(f"Found {len(whoosh_results)} Whoosh results")
    for i, result in enumerate(whoosh_results, 1):
        logger.info(f"Result {i}: {result.name} at {result.address}")
    
    logger.info("\nTesting Mapbox search:")
    mapbox_results = mapbox_provider.search(query, limit=3)
    logger.info(f"Found {len(mapbox_results)} Mapbox results")
    for i, result in enumerate(mapbox_results, 1):
        logger.info(f"Result {i}: {result.name} at {result.address}")
    
    logger.info("\nTesting Google Places search:")
    google_results = google_places_provider.search(query, limit=3)
    logger.info(f"Found {len(google_results)} Google Places results")
    for i, result in enumerate(google_results, 1):
        logger.info(f"Result {i}: {result.name} at {result.address}")
    
    # Test the orchestrator
    logger.info("\nTesting search orchestrator:")
    combined_results = search_orchestrator.search(query, limit=5)
    logger.info(f"Found {len(combined_results)} combined results")
    for i, result in enumerate(combined_results, 1):
        logger.info(f"Result {i}: {result.name} at {result.address} (Source: {result.source})")

if __name__ == "__main__":
    test_search() 
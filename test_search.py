import logging
from search import MapboxSearchProvider, GooglePlacesSearchProvider
from dotenv import load_dotenv
import os

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def test_search():
    """Test both Mapbox and Google Places search functionality."""
    mapbox_provider = MapboxSearchProvider(access_token=os.getenv('MAPBOX_ACCESS_TOKEN'))
    google_provider = GooglePlacesSearchProvider(api_key=os.getenv('GOOGLE_PLACES_API_KEY'))
    
    # Test search
    query = "communal"
    
    logger.info("\nTesting Mapbox search:")
    mapbox_results = mapbox_provider.search(query)
    logger.info(f"Found {len(mapbox_results)} Mapbox results")
    for i, result in enumerate(mapbox_results, 1):
        logger.info(f"Result {i}: {result.name} at {result.address}")
    
    logger.info("\nTesting Google Places search:")
    google_results = google_provider.search(query)
    logger.info(f"Found {len(google_results)} Google Places results")
    for i, result in enumerate(google_results, 1):
        logger.info(f"Result {i}: {result.name} at {result.address}")

if __name__ == "__main__":
    test_search() 
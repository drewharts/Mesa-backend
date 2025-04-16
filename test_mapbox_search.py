import logging
from search import MapboxSearchProvider
from dotenv import load_dotenv
import os

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def test_mapbox_search():
    """Test the Mapbox search functionality."""
    mapbox_provider = MapboxSearchProvider(access_token=os.getenv('MAPBOX_ACCESS_TOKEN'))
    
    # Test search
    query = "communal"
    logger.info(f"Testing Mapbox search with query: {query}")
    
    results = mapbox_provider.search(query)
    
    logger.info(f"Found {len(results)} results")
    for i, result in enumerate(results, 1):
        logger.info(f"Result {i}: {result.name} at {result.address}")

if __name__ == "__main__":
    test_mapbox_search() 
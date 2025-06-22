import os
import logging
import firebase_admin
from firebase_admin import credentials, firestore
from search import WhooshSearchProvider
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def index_places_from_firestore():
    """Index places from Firestore into the Whoosh index."""
    # Use absolute path to the service account file
    cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                            "Firebase Admin SDK Service Account.json")
    
    logger.debug(f"Using credentials from: {cred_path}")
    
    try:
        # Initialize Firebase Admin SDK
        if not firebase_admin._apps:
            logger.debug("Initializing Firebase Admin SDK")
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        
        logger.debug("Getting Firestore client")
        db = firestore.client()
        
        # Initialize Whoosh search provider
        logger.debug("Initializing Whoosh search provider")
        whoosh_provider = WhooshSearchProvider()
        
        # Get all places from Firestore
        logger.debug("Fetching places from Firestore")
        places_ref = db.collection('places')
        places = places_ref.get()
        
        logger.info(f"Found {len(places)} places in Firestore")
        
        # Index each place
        with whoosh_provider.ix.writer() as writer:
            for place in places:
                place_data = place.to_dict()
                logger.debug(f"Processing place: {place_data.get('name', 'Unknown')}")
                
                # Extract data from the place document
                name = place_data.get('name', '')
                if not name:  # Skip places without names
                    logger.warning(f"Skipping place with ID {place.id} - no name found")
                    continue
                
                # Get coordinates
                coordinate = place_data.get('coordinate')
                latitude = coordinate.latitude if coordinate else None
                longitude = coordinate.longitude if coordinate else None
                
                # Create a document for the index - only index what we need
                writer.add_document(
                    name=name,  # This is the only field we'll search on
                    place_id=str(place.id),
                    # Store these fields for the response but don't search on them
                    address=place_data.get('address', ''),
                    latitude=latitude or 0.0,
                    longitude=longitude or 0.0
                )
                
                logger.debug(f"Indexed place: {name}")
        
        logger.info("Indexing completed successfully")
        
        # Force refresh the index to ensure we're using the latest data
        whoosh_provider.force_refresh()
        logger.info("Whoosh index refreshed after indexing")
        
    except Exception as e:
        logger.error(f"Error indexing places: {str(e)}", exc_info=True)

if __name__ == "__main__":
    index_places_from_firestore() 
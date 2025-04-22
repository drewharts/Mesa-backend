from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
import logging
import tempfile
import sys
from search import WhooshSearchProvider, MapboxSearchProvider, GooglePlacesSearchProvider, SearchOrchestrator
from search.storage import PlaceStorage
import whoosh
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.analysis import StandardAnalyzer
from search.detail_place import DetailPlace
from search.search_result import SearchResult

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables

app = Flask(__name__)

# Create a persistent directory for Whoosh index
whoosh_index_dir = os.getenv('WHOOSH_INDEX_DIR', 'whoosh_index')
os.makedirs(whoosh_index_dir, exist_ok=True)
logger.info(f"Using Whoosh index directory: {whoosh_index_dir}")

# Initialize search providers
try:
    # Initialize Whoosh with schema
    schema = Schema(
        name=TEXT(stored=True, analyzer=StandardAnalyzer()),
        place_id=ID(stored=True),
        address=STORED,
        latitude=STORED,
        longitude=STORED
    )
    if not whoosh.index.exists_in(whoosh_index_dir):
        whoosh.index.create_in(whoosh_index_dir, schema)
        # Populate the index from Firestore if it's empty
        try:
            from index_places import index_places_from_firestore
            logger.info("Populating Whoosh index from Firestore...")
            index_places_from_firestore()
            logger.info("Whoosh index population completed")
        except Exception as e:
            logger.error(f"Error populating Whoosh index: {str(e)}")
    whoosh_provider = WhooshSearchProvider(index_path=whoosh_index_dir)
    logger.info("Whoosh search provider initialized successfully")
except Exception as e:
    logger.error(f"Error initializing Whoosh search provider: {str(e)}")
    whoosh_provider = None

try:
    mapbox_token = os.getenv('MAPBOX_ACCESS_TOKEN')
    if mapbox_token:
        mapbox_provider = MapboxSearchProvider(access_token=mapbox_token)
        logger.info("Mapbox search provider initialized successfully")
    else:
        logger.warning("MAPBOX_ACCESS_TOKEN not set. Mapbox provider disabled.")
        mapbox_provider = None
except Exception as e:
    logger.error(f"Error initializing Mapbox search provider: {str(e)}")
    mapbox_provider = None

try:
    google_key = os.getenv('GOOGLE_PLACES_API_KEY')
    if google_key:
        google_places_provider = GooglePlacesSearchProvider(api_key=google_key)
        logger.info("Google Places search provider initialized successfully")
    else:
        logger.warning("GOOGLE_PLACES_API_KEY not set. Google Places provider disabled.")
        google_places_provider = None
except Exception as e:
    logger.error(f"Error initializing Google Places search provider: {str(e)}")
    google_places_provider = None

# Initialize search orchestrator with available providers
search_orchestrator = SearchOrchestrator(
    whoosh_provider=whoosh_provider,
    mapbox_provider=mapbox_provider,
    google_places_provider=google_places_provider
)

@app.route('/', methods=['GET'])
def index():
    """Root endpoint that returns basic API information"""
    return jsonify({
        "name": "Mesa Backend API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": [
            {"path": "/", "methods": ["GET"], "description": "This endpoint - API information"},
            {"path": "/health", "methods": ["GET"], "description": "Health check endpoint"},
            {"path": "/search/suggestions", "methods": ["GET"], "description": "Get search suggestions"},
            {"path": "/search/place-details", "methods": ["GET"], "description": "Get place details"}
        ]
    })

@app.route('/search/suggestions', methods=['GET'])
def search_suggestions():
    try:
        query = request.args.get('query')
        limit = min(int(request.args.get('limit', 5)), 5)  # Cap at 5 results
        provider = request.args.get('provider', 'all').lower()
        
        # Get location parameters
        latitude = request.args.get('latitude')
        longitude = request.args.get('longitude')
        
        # Convert to float if provided
        if latitude is not None:
            latitude = float(latitude)
        if longitude is not None:
            longitude = float(longitude)
        
        logger.debug(f"Search suggestions request - Query: {query}, Provider: {provider}, Limit: {limit}, Location: ({latitude}, {longitude})")
        
        if not query:
            logger.warning("No query parameter provided")
            return jsonify({
                "error": "Query parameter is required"
            }), 400
            
        # Use specific provider if requested
        if provider == 'local':
            logger.debug("Using local database search")
            if whoosh_provider is None:
                return jsonify({"error": "Local search provider is not available"}), 503
            results = whoosh_provider.search(query, limit)
        elif provider == 'mapbox':
            logger.debug("Using Mapbox search")
            if mapbox_provider is None:
                return jsonify({"error": "Mapbox search provider is not available"}), 503
            results = mapbox_provider.search(query, limit, latitude, longitude)
        elif provider == 'google':
            logger.debug("Using Google Places search")
            if google_places_provider is None:
                return jsonify({"error": "Google Places search provider is not available"}), 503
            results = google_places_provider.search(query, limit, latitude, longitude)
        elif provider == 'all':
            logger.debug("Using all search providers")
            # Check if any providers are available
            if not any([whoosh_provider, mapbox_provider, google_places_provider]):
                return jsonify({"error": "No search providers are available", "suggestions": []}), 200
            results = search_orchestrator.search(query, limit, latitude, longitude)
        else:
            logger.warning(f"Invalid provider specified: {provider}")
            return jsonify({
                "error": "Invalid provider. Must be one of: local, mapbox, google, all"
            }), 400
        
        logger.debug(f"Found {len(results)} results")
        
        # Convert results to a simplified format for suggestions
        suggestions = []
        for result in results:
            suggestion = {
                "id": result.place_id,
                "name": result.name,
                "address": result.address,
                "source": result.source,
                "location": {
                    "latitude": result.latitude,
                    "longitude": result.longitude
                }
            }
            suggestions.append(suggestion)
            
        return jsonify({
            "suggestions": suggestions
        })
        
    except Exception as e:
        logger.error(f"Error during search suggestions: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/search/place-details', methods=['GET'])
def get_place_details():
    try:
        place_id = request.args.get('place_id')
        provider = request.args.get('provider')
        
        if not place_id or not provider:
            return jsonify({
                "error": "place_id and provider parameters are required"
            }), 400
            
        # Get place details based on provider
        if provider == 'local':
            if whoosh_provider is None:
                return jsonify({"error": "Local search provider is not available"}), 503
            try:
                detail_place = whoosh_provider.get_place_details(place_id)
            except ValueError as e:
                return jsonify({"error": str(e)}), 404
        elif provider == 'mapbox':
            if mapbox_provider is None:
                return jsonify({"error": "Mapbox search provider is not available"}), 503
            detail_place = mapbox_provider.get_place_details(place_id)
        elif provider == 'google':
            if google_places_provider is None:
                return jsonify({"error": "Google Places search provider is not available"}), 503
            detail_place = google_places_provider.get_place_details(place_id)
        else:
            return jsonify({
                "error": "Invalid provider. Must be one of: local, mapbox, google"
            }), 400
            
        # Save to local database if not already there
        if provider != 'local' and whoosh_provider is not None:
            try:
                # Convert DetailPlace to SearchResult for saving to Whoosh only
                search_result = SearchResult(
                    name=detail_place.name,
                    address=detail_place.address,
                    latitude=detail_place.coordinate.latitude,
                    longitude=detail_place.coordinate.longitude,
                    place_id=detail_place.mapbox_id if provider == 'mapbox' else detail_place.google_places_id,  # Use the correct provider-specific ID
                    source=provider
                )
                
                # Save to Whoosh index
                whoosh_provider.save_place(search_result)
                logger.info(f"Saved place to Whoosh index: {detail_place.name}")
                
                # Save to Firestore using the DetailPlace object directly
                try:
                    storage = PlaceStorage()
                    
                    # Check if place already exists in Firestore - look up by provider-specific ID
                    places_ref = storage.db.collection('places')
                    
                    # Check by Google Places ID or Mapbox ID based on the provider
                    if provider == 'google' and detail_place.google_places_id:
                        existing_places = places_ref.where('googlePlacesId', '==', detail_place.google_places_id).get()
                    elif provider == 'mapbox' and detail_place.mapbox_id:
                        existing_places = places_ref.where('mapboxId', '==', detail_place.mapbox_id).get()
                    else:
                        existing_places = []
                        
                    if existing_places:
                        # Place already exists
                        existing_id = existing_places[0].id
                        logger.info(f"Place already exists in Firestore with ID: {existing_id}")
                    else:
                        # Place doesn't exist, save it
                        # Use the DetailPlace to_firestore_dict method
                        place_data = detail_place.to_firestore_dict()
                        # Save to Firestore with a document ID matching the DetailPlace ID
                        doc_ref = places_ref.document(detail_place.id).set(place_data)
                        logger.info(f"Saved new place to Firestore with ID: {detail_place.id}")
                except Exception as e:
                    logger.error(f"Error saving to Firestore: {str(e)}")
            except Exception as e:
                logger.error(f"Error saving place: {str(e)}")
                
        # Return detailed place information in DetailPlace format
        return jsonify({
            "place": detail_place.to_dict()
        })
        
    except Exception as e:
        logger.error(f"Error getting place details: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Railway"""
    # Log environment information
    logger.info("Health check called")
    logger.info(f"Environment variables: PORT={os.getenv('PORT')}, "
               f"MAPBOX_TOKEN_SET={os.getenv('MAPBOX_ACCESS_TOKEN') is not None}, "
               f"GOOGLE_KEY_SET={os.getenv('GOOGLE_PLACES_API_KEY') is not None}")
    
    # Return basic health status if we at least got this far
    health_status = {
        "status": "ok",
        "providers": {
            "whoosh": whoosh_provider is not None,
            "mapbox": mapbox_provider is not None,
            "google_places": google_places_provider is not None
        },
        "environment": {
            "python_version": sys.version,
            "flask_running": True
        }
    }
    
    logger.info(f"Health status: {health_status}")
    return jsonify(health_status), 200

@app.route('/admin/reindex', methods=['POST'])
def reindex_places():
    """Admin endpoint to manually trigger reindexing of places from Firestore"""
    try:
        from index_places import index_places_from_firestore
        logger.info("Manual reindex triggered")
        
        # Clear the Whoosh index first
        if whoosh_provider is not None:
            whoosh_provider.clear_index()
            logger.info("Whoosh index cleared before reindexing")
        else:
            logger.warning("Whoosh provider not available, skipping index clear")
            
        # Reindex from Firestore
        index_places_from_firestore()
        logger.info("Reindex completed successfully")
        return jsonify({"status": "success", "message": "Reindex completed successfully"}), 200
    except Exception as e:
        logger.error(f"Error during reindex: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)

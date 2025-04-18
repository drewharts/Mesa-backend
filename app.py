from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
import logging
from search import WhooshSearchProvider, MapboxSearchProvider, GooglePlacesSearchProvider, SearchOrchestrator
from search.storage import PlaceStorage

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables

app = Flask(__name__)

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
            results = whoosh_provider.search(query, limit)
        elif provider == 'mapbox':
            logger.debug("Using Mapbox search")
            results = mapbox_provider.search(query, limit, latitude, longitude)
        elif provider == 'google':
            logger.debug("Using Google Places search")
            results = google_places_provider.search(query, limit, latitude, longitude)
        elif provider == 'all':
            logger.debug("Using all search providers")
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
        source = request.args.get('source')
        
        if not place_id or not source:
            return jsonify({
                "error": "place_id and source parameters are required"
            }), 400
            
        # Get place details based on source
        if source == 'local':
            # Search in local database
            results = whoosh_provider.search(place_id, limit=1)
            if not results:
                return jsonify({"error": "Place not found"}), 404
            place = results[0]
        elif source == 'mapbox':
            # Get details from Mapbox
            place = mapbox_provider.get_place_details(place_id)
        elif source == 'google':
            # Get details from Google Places
            place = google_places_provider.get_place_details(place_id)
        else:
            return jsonify({
                "error": "Invalid source. Must be one of: local, mapbox, google"
            }), 400
            
        # Save to local database if not already there
        if source != 'local':
            try:
                # Save to Whoosh index
                whoosh_provider.save_place(place)
                logger.info(f"Saved place to Whoosh index: {place.name}")
                
                # Save to Firestore
                storage = PlaceStorage()
                firestore_id = storage.save_place(place)
                logger.info(f"Saved place to Firestore with ID: {firestore_id}")
            except Exception as e:
                logger.error(f"Error saving place: {str(e)}")
                
        # Return detailed place information
        return jsonify({
            "place": {
                "id": place.place_id,
                "name": place.name,
                "address": place.address,
                "location": {
                    "latitude": place.latitude,
                    "longitude": place.longitude
                },
                "source": place.source,
                "additional_data": place.additional_data
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting place details: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=True)

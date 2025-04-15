from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
import logging
from search import WhooshSearchProvider, MapboxSearchProvider, GooglePlacesSearchProvider, SearchOrchestrator

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

@app.route('/search', methods=['GET'])
def search():
    try:
        query = request.args.get('query')
        limit = int(request.args.get('limit', 10))
        provider = request.args.get('provider', 'all').lower()
        
        # Get location parameters
        latitude = request.args.get('latitude')
        longitude = request.args.get('longitude')
        
        # Convert to float if provided
        if latitude is not None:
            latitude = float(latitude)
        if longitude is not None:
            longitude = float(longitude)
        
        logger.debug(f"Search request - Query: {query}, Provider: {provider}, Limit: {limit}, Location: ({latitude}, {longitude})")
        
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
        
        # Convert results to GeoJSON format
        features = []
        for result in results:
            logger.debug(f"Processing result: {result.name} ({result.source})")
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [result.longitude, result.latitude]
                },
                "properties": {
                    "name": result.name,
                    "address": result.address,
                    "place_id": result.place_id,
                    "source": result.source,
                    **result.additional_data
                }
            }
            features.append(feature)
            
        return jsonify({
            "type": "FeatureCollection",
            "features": features
        })
        
    except Exception as e:
        logger.error(f"Error during search: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)

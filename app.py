from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
import logging
import tempfile
import sys
import requests
from firebase_admin import firestore
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

# Initialize place storage for nearby places endpoint
place_storage = PlaceStorage()

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
            {"path": "/search/place-details", "methods": ["GET"], "description": "Get place details"},
            {"path": "/nearby-places", "methods": ["GET"], "description": "Get nearby places"}
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
                # First save to Firestore to get the correct document ID
                storage = PlaceStorage()
                # Create SearchResult with original external ID for duplicate checking
                search_result_for_duplicate_check = SearchResult(
                    name=detail_place.name,
                    address=detail_place.address,
                    latitude=detail_place.coordinate.latitude,
                    longitude=detail_place.coordinate.longitude,
                    place_id=detail_place.id,  # Original external ID for duplicate checking
                    source=provider
                )
                
                # Check if place already exists in Firestore
                existing_id = storage._check_for_duplicate(search_result_for_duplicate_check)
                firestore_document_id = None
                
                if not existing_id:
                    # Get Firestore connection from storage
                    if hasattr(storage, 'db'):
                        places_ref = storage.db.collection('places')
                        # Use the DetailPlace to_firestore_dict method
                        place_data = detail_place.to_firestore_dict()
                        # Save to Firestore
                        doc_ref = places_ref.add(place_data)
                        firestore_document_id = doc_ref[1].id
                        logger.info(f"Saved place to Firestore with ID: {firestore_document_id}")
                else:
                    firestore_document_id = existing_id
                    logger.info(f"Place already exists in Firestore with ID: {existing_id}")
                
                # Now create SearchResult with Firestore document ID for Whoosh
                if firestore_document_id:
                    search_result_for_whoosh = SearchResult(
                        name=detail_place.name,
                        address=detail_place.address,
                        latitude=detail_place.coordinate.latitude,
                        longitude=detail_place.coordinate.longitude,
                        place_id=firestore_document_id,  # Use Firestore document ID for Whoosh
                        source=provider
                    )
                    
                    # Save to Whoosh index with Firestore document ID
                    whoosh_provider.save_place(search_result_for_whoosh)
                    logger.info(f"Saved place to Whoosh index with Firestore ID: {detail_place.name}")
                    
                    # Update the detail_place ID to match the Firestore ID
                    detail_place.id = firestore_document_id
                    
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
        
        # Force refresh the index to ensure we're using the latest data
        if whoosh_provider is not None:
            whoosh_provider.force_refresh()
            logger.info("Whoosh index refreshed after reindexing")
        
        return jsonify({"status": "success", "message": "Reindex completed successfully"}), 200
    except Exception as e:
        logger.error(f"Error during reindex: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/admin/index-status', methods=['GET'])
def get_index_status():
    """Admin endpoint to check the Whoosh index status"""
    try:
        if whoosh_provider is None:
            return jsonify({
                "status": "error", 
                "message": "Whoosh provider not available"
            }), 503
        
        index_info = whoosh_provider.get_index_info()
        return jsonify({
            "status": "success",
            "index_info": index_info
        }), 200
    except Exception as e:
        logger.error(f"Error getting index status: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/admin/refresh-index', methods=['POST'])
def refresh_index():
    """Admin endpoint to force refresh the Whoosh index"""
    try:
        if whoosh_provider is None:
            return jsonify({
                "status": "error", 
                "message": "Whoosh provider not available"
            }), 503
        
        whoosh_provider.force_refresh()
        logger.info("Manual index refresh completed")
        
        # Get updated index info
        index_info = whoosh_provider.get_index_info()
        
        return jsonify({
            "status": "success", 
            "message": "Index refreshed successfully",
            "index_info": index_info
        }), 200
    except Exception as e:
        logger.error(f"Error refreshing index: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/nearby-places', methods=['GET'])
def nearby_places():
    """
    Endpoint to find nearby places using Google Places API Nearby Search
    First checks local database for existing places within 50m radius before calling Google API
    Expected parameters:
    - latitude: float (required)
    - longitude: float (required)
    - radius: int (optional, default 50, max 50000 meters)
    - type: string (optional, place type filter)
    - limit: int (optional, default 20, max 60)
    """
    try:
        # Get required coordinates
        latitude = request.args.get('latitude')
        longitude = request.args.get('longitude')
        
        if not latitude or not longitude:
            logger.warning("Missing latitude or longitude parameters")
            return jsonify({
                "error": "Both latitude and longitude parameters are required"
            }), 400
            
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            logger.warning("Invalid latitude or longitude values")
            return jsonify({
                "error": "Latitude and longitude must be valid numbers"
            }), 400
        
        # Get optional parameters
        radius = int(request.args.get('radius', 50))  # Default 50 meters
        place_type = request.args.get('type')  # Optional place type filter
        limit = int(request.args.get('limit', 20))  # Default 20 results
        
        # Validate radius (Google Places API limit)
        if radius > 50000:
            radius = 50000
        elif radius < 1:
            radius = 1
            
        # Validate limit
        if limit > 60:  # Google Places API limit
            limit = 60
        elif limit < 1:
            limit = 1
        
        logger.debug(f"Nearby places request - Lat: {latitude}, Lng: {longitude}, Radius: {radius}m, Type: {place_type}, Limit: {limit}")
        
        # FIRST: Check if we have existing places within 50 meters in our database
        existing_places = []
        try:
            logger.debug("Checking for existing places within 50 meters in local database")
            existing_places = place_storage.find_nearby_places(latitude, longitude, 50, limit)
            logger.debug(f"Found {len(existing_places)} existing places within 50 meters")
        except Exception as e:
            logger.error(f"Error checking local database: {str(e)}")
        
        # If we have existing places within 50 meters, use them instead of calling Google API
        if existing_places:
            logger.debug("Using existing places from local database instead of calling Google API")
            
            # Convert to GeoJSON format
            features = []
            for place in existing_places:
                feature = {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [place.longitude, place.latitude]
                    },
                    "properties": {
                        "name": place.name,
                        "address": place.address,
                        "place_id": place.place_id,
                        "source": f"{place.source}_cached",
                        "distance_meters": place.additional_data.get('distance_meters'),
                        **{k: v for k, v in place.additional_data.items() if k not in ['firestore_id', 'distance_meters']}
                    }
                }
                features.append(feature)
            
            return jsonify({
                "type": "FeatureCollection",
                "features": features,
                "metadata": {
                    "search_location": {
                        "latitude": latitude,
                        "longitude": longitude
                    },
                    "radius_meters": radius,
                    "place_type": place_type,
                    "total_results": len(features),
                    "data_source": "local_database",
                    "cache_hit": True
                }
            })
        
        # If no existing places found, proceed with Google API call
        logger.debug("No existing places found within 50 meters, calling Google Places API")
        
        # Use Google Places API Nearby Search
        api_key = os.getenv('GOOGLE_PLACES_API_KEY')
        if not api_key:
            logger.error("Google Places API key not configured")
            return jsonify({
                "error": "Google Places API key not configured"
            }), 500
        
        # Build the API request URL
        base_url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{latitude},{longitude}",
            "radius": radius,
            "key": api_key
        }
        
        # Add place type filter if specified
        if place_type:
            params["type"] = place_type
        
        logger.debug(f"Making request to Google Places API with params: {params}")
        
        # Make the API request
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "OK":
            logger.error(f"Google Places API error: {data.get('status')} - {data.get('error_message', 'Unknown error')}")
            return jsonify({
                "error": f"Google Places API error: {data.get('status')}"
            }), 500
        
        # Process the results and save them to our database
        places = data.get("results", [])[:limit]  # Limit results as requested
        logger.debug(f"Found {len(places)} nearby places from Google API")
        
        # Convert to GeoJSON format and save to database
        features = []
        saved_to_whoosh = 0
        saved_to_firestore = 0
        
        for place in places:
            geometry = place.get("geometry", {})
            location = geometry.get("location", {})
            
            # Save to local database with comprehensive duplicate prevention and immediate indexing
            try:
                # Create SearchResult to check for duplicates (same as GooglePlacesSearchProvider)
                search_result = SearchResult(
                    name=place.get("name", ""),
                    address=place.get("vicinity", ""),  # Nearby API uses 'vicinity' instead of 'formatted_address'
                    latitude=location.get("lat"),
                    longitude=location.get("lng"),
                    place_id=place.get("place_id"),
                    source="google"  # Use 'google' source to match duplicate checking logic
                )
                
                # Check if this place already exists (same pattern as GooglePlacesSearchProvider)
                existing_id = place_storage._check_for_duplicate(search_result)
                
                # Determine the Firestore document ID to use for Whoosh
                firestore_document_id = None
                
                if existing_id:
                    logger.debug(f"Place already exists in database: {search_result.name} (ID: {existing_id})")
                    firestore_document_id = existing_id
                else:
                    # Save new place using same structure as GooglePlacesSearchProvider
                    import uuid
                    place_uuid = str(uuid.uuid4()).upper()
                    
                    # Save directly to Firestore with proper structure (same as GooglePlacesSearchProvider)
                    if place_storage.db:
                        places_ref = place_storage.db.collection('places')
                        place_data = {
                            'id': place_uuid,
                            'name': place.get("name", ""),
                            'address': place.get("vicinity", ""),  # Nearby API uses 'vicinity'
                            'city': "",  # Nearby API doesn't provide detailed address components
                            'googlePlacesId': place.get("place_id"),
                            'mapboxId': None,  # Not applicable for Google Places
                            'coordinate': firestore.GeoPoint(location.get("lat"), location.get("lng")),
                            'categories': place.get("types", []),
                            'phone': None,  # Not provided by Nearby Search API
                            'rating': place.get("rating"),
                            'openHours': [],  # Not provided by Nearby Search API
                            'description': place.get("vicinity", ""),
                            'priceLevel': str(place.get("price_level")) if place.get("price_level") is not None else None,
                            'reservable': None,
                            'servesBreakfast': None,
                            'servesLunch': None,
                            'servesDinner': None,
                            'instagram': None,
                            'twitter': None
                        }
                        
                        # Create document with specific ID (same as GooglePlacesSearchProvider)
                        doc_ref = places_ref.document(place_uuid)
                        doc_ref.set(place_data)
                        saved_to_firestore += 1
                        firestore_document_id = place_uuid
                        logger.debug(f"Saved new place to Firestore: {search_result.name} (ID: {place_uuid})")
                
                # Save to Whoosh with Firestore document ID
                if whoosh_provider is not None and firestore_document_id:
                    try:
                        # Create SearchResult with Firestore document ID for Whoosh
                        search_result_for_whoosh = SearchResult(
                            name=place.get("name", ""),
                            address=place.get("vicinity", ""),
                            latitude=location.get("lat"),
                            longitude=location.get("lng"),
                            place_id=firestore_document_id,  # Use Firestore document ID
                            source="google"
                        )
                        whoosh_provider.save_place(search_result_for_whoosh)
                        saved_to_whoosh += 1
                        logger.debug(f"Saved place to Whoosh index with Firestore ID: {search_result.name}")
                    except Exception as e:
                        logger.error(f"Error saving to Whoosh index: {str(e)}")
                        
            except Exception as e:
                logger.error(f"Error in caching process for place {place.get('name', 'Unknown')}: {str(e)}")
            
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [location.get("lng"), location.get("lat")]
                },
                "properties": {
                    "name": place.get("name", ""),
                    "address": place.get("vicinity", ""),
                    "place_id": place.get("place_id"),
                    "source": "google_places_nearby",
                    "rating": place.get("rating"),
                    "user_ratings_total": place.get("user_ratings_total"),
                    "price_level": place.get("price_level"),
                    "types": place.get("types", []),
                    "business_status": place.get("business_status"),
                    "permanently_closed": place.get("permanently_closed", False)
                }
            }
            
            # Add optional fields if available
            if "opening_hours" in place:
                feature["properties"]["open_now"] = place["opening_hours"].get("open_now")
            
            if "photos" in place and place["photos"]:
                # Add photo reference for the first photo
                feature["properties"]["photo_reference"] = place["photos"][0].get("photo_reference")
            
            features.append(feature)
        
        logger.info(f"Caching summary: {saved_to_whoosh}/{len(places)} places saved to Whoosh, {saved_to_firestore}/{len(places)} places saved to Firestore")
        logger.debug(f"Returning {len(features)} nearby places from Google API")
        
        return jsonify({
            "type": "FeatureCollection",
            "features": features,
            "metadata": {
                "search_location": {
                    "latitude": latitude,
                    "longitude": longitude
                },
                "radius_meters": radius,
                "place_type": place_type,
                "total_results": len(features),
                "data_source": "google_places_api",
                "cache_hit": False,
                "caching_summary": {
                    "places_cached_to_whoosh": saved_to_whoosh,
                    "places_cached_to_firestore": saved_to_firestore,
                    "total_places_processed": len(places)
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Error during nearby places search: {str(e)}", exc_info=True)
        return jsonify({
            "error": str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)

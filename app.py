from flask import Flask, request, jsonify, g
from flask_cors import CORS
from dotenv import load_dotenv
import os
import logging
import tempfile
import sys
import requests
import time
from firebase_admin import firestore
from auth_middleware import require_auth, optional_auth, require_admin
from search import WhooshSearchProvider, MapboxSearchProvider, GooglePlacesSearchProvider, SearchOrchestrator
from search.storage import PlaceStorage
import whoosh
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.analysis import StandardAnalyzer
from search.detail_place import DetailPlace
from search.search_result import SearchResult
from url_processors.orchestrator import URLProcessorOrchestrator
from url_processors.geocoding_service import GeocodingService

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

load_dotenv()  # Load environment variables

app = Flask(__name__)
# Enable CORS for all routes
CORS(app)

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
@optional_auth
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
@require_admin
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
@require_admin
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
@require_admin
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

@app.route('/process-url', methods=['POST'])
@optional_auth  # Use optional_auth to allow both authenticated and anonymous usage
def process_url():
    """Process a URL to extract location information.
    
    Expected JSON body:
    {
        "url": "https://www.tiktok.com/@user/video/123456"
    }
    
    Returns:
    {
        "processor_type": "tiktok",
        "data": {...},
        "location_info": {
            "location_name": "...",
            "coordinates": [lat, lon],
            "formatted_address": "...",
            "place_id": "..."
        }
    }
    """
    try:
        # Get JSON data with force=True to handle parsing errors
        try:
            data = request.get_json(force=True)
        except Exception as json_error:
            logger.error(f"JSON parsing error: {str(json_error)}")
            # Try to get raw data and clean it
            raw_data = request.get_data(as_text=True)
            logger.debug(f"Raw request data: {repr(raw_data)}")
            
            # Try to parse after cleaning common issues
            import json
            import re
            # Remove control characters
            cleaned_data = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', raw_data)
            try:
                data = json.loads(cleaned_data)
            except:
                return jsonify({"error": "Invalid JSON in request body"}), 400
        
        if not data or 'url' not in data:
            return jsonify({"error": "Missing 'url' in request body"}), 400
        
        url = data['url']
        
        # Clean the URL of any control characters
        import re
        url = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', url).strip()
        
        # Initialize processors
        orchestrator = URLProcessorOrchestrator()
        geocoding_service = GeocodingService()
        
        # Process the URL
        try:
            result = orchestrator.process_url(url)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        
        # If location info was extracted, try to geocode it
        location_info = result.get('location_info')
        if location_info:
            # If we have a location name but no coordinates, geocode it
            if location_info.get('location_name') and not location_info.get('coordinates'):
                geocoded = geocoding_service.geocode_location(location_info['location_name'])
                if geocoded:
                    location_info.update({
                        'coordinates': geocoded['coordinates'],
                        'formatted_address': geocoded['formatted_address'],
                        'place_id': geocoded['place_id'],
                        'address_components': geocoded['components']
                    })
            
            # If we have coordinates but no address, reverse geocode
            elif location_info.get('coordinates') and not location_info.get('formatted_address'):
                lat, lon = location_info['coordinates']
                reverse_geocoded = geocoding_service.reverse_geocode(lat, lon)
                if reverse_geocoded:
                    location_info.update({
                        'formatted_address': reverse_geocoded['formatted_address'],
                        'place_id': reverse_geocoded['place_id'],
                        'address_components': reverse_geocoded['components']
                    })
        
        # Update result with enhanced location info
        result['location_info'] = location_info
        
        # Check for existing places BEFORE making API calls to reduce Google API usage
        place_saved = False
        existing_place_id = None
        
        # Get user ID from authenticated user (if authenticated)
        user_id = None
        if g.user:
            user_id = g.user.get('uid')
            logger.info(f"Processing URL for authenticated user: {user_id}")
        
        if location_info and location_info.get('coordinates') and location_info.get('location_name'):
            try:
                from search.storage import PlaceStorage
                from search.base import SearchResult
                
                storage = PlaceStorage()
                
                # First check if we already have this TikTok URL
                if 'tiktok' in url.lower():
                    existing_place_id = storage.check_for_existing_place_by_tiktok_url(url)
                    if existing_place_id:
                        logger.info(f"Found existing place by TikTok URL: {existing_place_id}")
                
                # If no TikTok match, check by name and location
                if not existing_place_id:
                    lat, lon = location_info['coordinates']
                    existing_place_id = storage.check_for_existing_place_by_name_and_location(
                        location_info.get('location_name', ''), lat, lon
                    )
                    if existing_place_id:
                        logger.info(f"Found existing place by name and location: {existing_place_id}")
                
                # If we found an existing place, just add TikTok video if needed and associate with user
                if existing_place_id:
                    if 'tiktok' in url.lower() and result.get('data'):
                        data = result['data']
                        tiktok_videos = [{
                            'video_id': data.get('video_id', ''),
                            'url': url,
                            'embed_html': data.get('embed_html', ''),
                            'thumbnail_url': data.get('thumbnail_url', ''),
                            'author': {
                                'username': data.get('author', {}).get('username', ''),
                                'display_name': data.get('author', {}).get('display_name', '')
                            },
                            'hashtags': data.get('hashtags', []),
                            'created_at': data.get('created_at', '')
                        }]
                        storage._append_tiktok_videos_to_place(existing_place_id, tiktok_videos)
                    
                    # Associate with user if user_id provided
                    if user_id:
                        # Create SearchResult for user association
                        lat, lon = location_info['coordinates']
                        search_result = SearchResult(
                            name=location_info.get('location_name', ''),
                            address=location_info.get('formatted_address', ''),
                            latitude=lat,
                            longitude=lon,
                            place_id=location_info.get('place_id', ''),
                            source='tiktok' if 'tiktok' in url.lower() else result.get('processor_type', 'url')
                        )
                        
                        # Add to user's external places
                        user_ref = storage.db.collection('users').document(user_id)
                        external_places_ref = user_ref.collection('externalPlaces')
                        
                        # Check if not already in user's external places
                        existing_external = external_places_ref.where('placeId', '==', existing_place_id).get()
                        if not existing_external:
                            external_place_data = {
                                'placeId': existing_place_id,
                                'name': search_result.name,
                                'address': search_result.address,
                                'coordinates': {
                                    'latitude': search_result.latitude,
                                    'longitude': search_result.longitude
                                },
                                'source': search_result.source,
                                'addedAt': firestore.SERVER_TIMESTAMP
                            }
                            doc_ref = external_places_ref.add(external_place_data)
                            result['external_place_id'] = doc_ref[1].id
                    
                    result['place_saved'] = True
                    result['place_id'] = existing_place_id
                    result['place_already_existed'] = True
                    place_saved = True
                    logger.info(f"Used existing place, avoided API calls: {existing_place_id}")
                    
                else:
                    # No existing place found, proceed with normal creation
                    # Create SearchResult from location info
                    lat, lon = location_info['coordinates']
                    search_result = SearchResult(
                        name=location_info.get('location_name', ''),
                        address=location_info.get('formatted_address', ''),
                        latitude=lat,
                        longitude=lon,
                        place_id=location_info.get('place_id', ''),
                        source='tiktok' if 'tiktok' in url.lower() else result.get('processor_type', 'url'),
                        additional_data={
                            'city': location_info.get('address_components', {}).get('locality', '') or location_info.get('city', ''),
                            'categories': []  # Will be populated below if it's a TikTok URL
                        }
                    )
                    
                    # Prepare TikTok video data if this is a TikTok URL
                    tiktok_videos = None
                    if 'tiktok' in url.lower() and result.get('data'):
                        data = result['data']
                        tiktok_videos = [{
                            'video_id': data.get('video_id', ''),
                            'url': url,
                            'embed_html': data.get('embed_html', ''),
                            'thumbnail_url': data.get('thumbnail_url', ''),
                            'author': {
                                'username': data.get('author', {}).get('username', ''),
                                'display_name': data.get('author', {}).get('display_name', '')
                            },
                            'hashtags': data.get('hashtags', []),
                            'created_at': data.get('created_at', '')
                        }]
                        
                        # Extract categories from hashtags
                        hashtags = data.get('hashtags', [])
                        categories = []
                        food_hashtags = ['food', 'foodie', 'restaurant', 'cafe', 'dining', 'eat', 'meal']
                        if any(tag.lower() in food_hashtags for tag in hashtags):
                            categories.extend(['restaurant', 'food'])
                        categories.extend(hashtags[:3])  # Add first few hashtags as categories
                        
                        # Update additional_data with categories and city
                        search_result.additional_data.update({
                            'categories': list(set(categories)),  # Remove duplicates
                            'city': location_info.get('address_components', {}).get('locality', '') or 
                                   location_info.get('city', '') or
                                   data.get('location', {}).get('city', '') if isinstance(data.get('location'), dict) else ''
                        })
                    
                    # Save new place
                    if user_id:
                        # Save to both places collection and user's externalPlaces
                        place_id, external_id = storage.add_place_to_user_external_places(
                            user_id, search_result, tiktok_videos
                        )
                        if place_id:
                            result['place_saved'] = True
                            result['place_id'] = place_id
                            result['external_place_id'] = external_id
                            place_saved = True
                            
                            # Trigger reindex in background (optional)
                            # storage.trigger_whoosh_reindex()
                    else:
                        # Just save to places collection without user association
                        place_id = storage.save_place_with_tiktok_data(search_result, tiktok_videos)
                        if place_id:
                            result['place_saved'] = True
                            result['place_id'] = place_id
                            place_saved = True
                        
            except Exception as e:
                logger.error(f"Error saving place from URL processing: {str(e)}")
                result['place_save_error'] = str(e)
        
        # Log the processed URL
        logger.info(f"Processed URL: {url}, Type: {result.get('processor_type')}, "
                   f"Location found: {location_info is not None}, Place saved: {place_saved}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error processing URL: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route('/process-url/platforms', methods=['GET'])
def get_supported_platforms():
    """Get list of supported platforms for URL processing."""
    orchestrator = URLProcessorOrchestrator()
    return jsonify({
        "supported_platforms": orchestrator.get_supported_platforms()
    })

@app.route('/privacy-policy', methods=['GET'])
def privacy_policy():
    """Privacy policy endpoint required for TikTok API integration."""
    privacy_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Privacy Policy - Mesa Location Services</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                color: #333;
            }
            h1, h2 { color: #2c3e50; }
            .last-updated { color: #666; font-style: italic; }
            .section { margin-bottom: 2em; }
        </style>
    </head>
    <body>
        <h1>Privacy Policy</h1>
        <p class="last-updated">Last updated: """ + time.strftime("%B %d, %Y") + """</p>
        
        <div class="section">
            <h2>1. Information We Collect</h2>
            <p>Mesa Location Services ("we," "our," or "us") is a location-based content discovery service. We collect the following information:</p>
            <ul>
                <li><strong>URL Data:</strong> Social media URLs you submit for location extraction</li>
                <li><strong>Location Information:</strong> Geographic data extracted from social media content</li>
                <li><strong>Usage Data:</strong> API usage statistics and error logs for service improvement</li>
            </ul>
        </div>

        <div class="section">
            <h2>2. How We Use Your Information</h2>
            <p>We use the collected information to:</p>
            <ul>
                <li>Extract and provide location information from social media content</li>
                <li>Improve our location extraction algorithms</li>
                <li>Maintain and optimize our service performance</li>
                <li>Comply with legal obligations and platform requirements</li>
            </ul>
        </div>

        <div class="section">
            <h2>3. Data Sharing and Third Parties</h2>
            <p>We integrate with the following third-party services:</p>
            <ul>
                <li><strong>TikTok API:</strong> To extract video metadata and location information</li>
                <li><strong>Google Maps API:</strong> For geocoding location names to coordinates</li>
                <li><strong>Firestore:</strong> For data storage and caching</li>
            </ul>
            <p>We do not sell, trade, or otherwise transfer your personal information to third parties except as described in this policy.</p>
        </div>

        <div class="section">
            <h2>4. Data Retention</h2>
            <p>We retain extracted location data for caching purposes to improve service performance. Data is automatically purged based on usage patterns and storage limitations.</p>
        </div>

        <div class="section">
            <h2>5. Data Security</h2>
            <p>We implement appropriate security measures to protect your information, including:</p>
            <ul>
                <li>Encrypted data transmission (HTTPS)</li>
                <li>Secure API authentication and access controls</li>
                <li>Regular security monitoring and updates</li>
            </ul>
        </div>

        <div class="section">
            <h2>6. Your Rights</h2>
            <p>You have the right to:</p>
            <ul>
                <li>Request information about data we have collected</li>
                <li>Request deletion of your data</li>
                <li>Opt out of data collection</li>
                <li>Contact us with privacy concerns</li>
            </ul>
        </div>

        <div class="section">
            <h2>7. Children's Privacy</h2>
            <p>Our service is not intended for children under 13. We do not knowingly collect personal information from children under 13.</p>
        </div>

        <div class="section">
            <h2>8. Changes to This Policy</h2>
            <p>We may update this privacy policy from time to time. The updated date will be reflected at the top of this page.</p>
        </div>

        <div class="section">
            <h2>9. Contact Information</h2>
            <p>If you have questions about this privacy policy or our data practices, please contact us at:</p>
            <p>
                <strong>Email:</strong> privacy@mesa-location-services.com<br>
                <strong>Service:</strong> Mesa Location Services API<br>
                <strong>Last Updated:</strong> """ + time.strftime("%B %d, %Y") + """
            </p>
        </div>

        <div class="section">
            <h2>10. Platform-Specific Information</h2>
            <h3>TikTok Integration</h3>
            <p>When processing TikTok URLs, we:</p>
            <ul>
                <li>Access only publicly available video metadata</li>
                <li>Extract location information from video captions and metadata</li>
                <li>Do not access private account information</li>
                <li>Comply with TikTok's API terms of service</li>
            </ul>
        </div>
    </body>
    </html>
    """
    return privacy_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/terms-of-service', methods=['GET'])
def terms_of_service():
    """Terms of service endpoint."""
    terms_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Terms of Service - Mesa Location Services</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                color: #333;
            }
            h1, h2 { color: #2c3e50; }
            .last-updated { color: #666; font-style: italic; }
            .section { margin-bottom: 2em; }
        </style>
    </head>
    <body>
        <h1>Terms of Service</h1>
        <p class="last-updated">Last updated: """ + time.strftime("%B %d, %Y") + """</p>
        
        <div class="section">
            <h2>1. Acceptance of Terms</h2>
            <p>By using Mesa Location Services, you agree to these terms of service.</p>
        </div>

        <div class="section">
            <h2>2. Service Description</h2>
            <p>Mesa Location Services is an API that extracts location information from social media URLs for legitimate business and research purposes.</p>
        </div>

        <div class="section">
            <h2>3. Acceptable Use</h2>
            <p>You agree to use our service only for:</p>
            <ul>
                <li>Legitimate business purposes</li>
                <li>Research and analytics</li>
                <li>Content discovery and mapping</li>
                <li>Compliance with all applicable laws</li>
            </ul>
        </div>

        <div class="section">
            <h2>4. Prohibited Uses</h2>
            <p>You may not use our service to:</p>
            <ul>
                <li>Violate any laws or regulations</li>
                <li>Infringe on privacy rights</li>
                <li>Harvest personal information</li>
                <li>Spam or abuse the service</li>
            </ul>
        </div>

        <div class="section">
            <h2>5. Data and Privacy</h2>
            <p>See our <a href="/privacy-policy">Privacy Policy</a> for information about data handling.</p>
        </div>

        <div class="section">
            <h2>6. Service Availability</h2>
            <p>We strive to maintain service availability but do not guarantee uninterrupted access.</p>
        </div>

        <div class="section">
            <h2>7. Contact</h2>
            <p>Questions about these terms? Contact us at: <strong>legal@mesa-location-services.com</strong></p>
        </div>
    </body>
    </html>
    """
    return terms_content, 200, {'Content-Type': 'text/html; charset=utf-8'}

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)

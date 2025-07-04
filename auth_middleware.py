from functools import wraps
from flask import request, jsonify, g
import firebase_admin
from firebase_admin import auth
import logging

logger = logging.getLogger(__name__)


def get_authenticated_user():
    """Extract and verify Firebase ID token from Authorization header.
    
    Returns:
        dict: User information including uid, email, etc. or None if not authenticated
    """
    try:
        # Get the Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None
            
        # Extract Bearer token
        parts = auth_header.split(' ')
        if len(parts) != 2 or parts[0] != 'Bearer':
            logger.warning("Invalid Authorization header format")
            return None
            
        id_token = parts[1]
        
        # Verify the ID token
        try:
            decoded_token = auth.verify_id_token(id_token)
            return decoded_token
        except auth.InvalidIdTokenError:
            logger.warning("Invalid ID token provided")
            return None
        except auth.ExpiredIdTokenError:
            logger.warning("Expired ID token provided")
            return None
        except Exception as e:
            logger.error(f"Error verifying ID token: {str(e)}")
            return None
            
    except Exception as e:
        logger.error(f"Error in get_authenticated_user: {str(e)}")
        return None


def require_auth(f):
    """Decorator to require authentication for an endpoint.
    
    Usage:
        @app.route('/protected')
        @require_auth
        def protected_endpoint():
            user = g.user  # Access authenticated user
            return jsonify({"user_id": user['uid']})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_authenticated_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        
        # Store user in Flask's g object for access in the endpoint
        g.user = user
        return f(*args, **kwargs)
    
    return decorated_function


def optional_auth(f):
    """Decorator to optionally authenticate for an endpoint.
    
    Usage:
        @app.route('/public-or-personalized')
        @optional_auth
        def endpoint():
            if g.user:
                # Personalized response for authenticated user
                return jsonify({"message": f"Hello {g.user['email']}!"})
            else:
                # Public response
                return jsonify({"message": "Hello anonymous!"})
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_authenticated_user()
        # Store user in g object (will be None if not authenticated)
        g.user = user
        return f(*args, **kwargs)
    
    return decorated_function


def require_admin(f):
    """Decorator to require admin authentication for an endpoint.
    
    Admin status can be determined by:
    1. Custom claims in the Firebase token
    2. A list of admin emails
    3. A Firestore collection of admin users
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_authenticated_user()
        if not user:
            return jsonify({"error": "Authentication required"}), 401
        
        # Check if user is admin (implement your admin logic here)
        # Option 1: Check custom claims
        is_admin = user.get('admin', False)
        
        # Option 2: Check against admin email list (example)
        # admin_emails = ['admin@example.com']
        # is_admin = user.get('email') in admin_emails
        
        if not is_admin:
            return jsonify({"error": "Admin access required"}), 403
        
        g.user = user
        return f(*args, **kwargs)
    
    return decorated_function
from firebase_admin import credentials, firestore, initialize_app
import os
import firebase_admin

class FirestoreService:
    def __init__(self):
        cred_path = os.getenv('FIRESTORE_CREDENTIALS')
        if not cred_path or not os.path.exists(cred_path):
            raise ValueError("Firestore credentials path not found")
        cred = credentials.Certificate(cred_path)
        initialize_app(cred)
        self.db = firestore.client()

    def get_all_places(self):
        """Fetch all places from Firestore."""
        places = self.db.collection('places').stream()
        return [
            {
                'id': doc.id,
                'name': doc.to_dict().get('name', ''),
                'address': doc.to_dict().get('address', ''),
                'latitude': doc.to_dict().get('latitude', 0.0),
                'longitude': doc.to_dict().get('longitude', 0.0)
            }
            for doc in places
        ]

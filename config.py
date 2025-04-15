import os

class Config:
    MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    WHOOSH_INDEX_DIR = 'indexdir'

    @staticmethod
    def validate():
        if not all([Config.MAPBOX_ACCESS_TOKEN, Config.GOOGLE_API_KEY]):
            raise ValueError("Missing API keys")
        if not os.path.exists(Config.WHOOSH_INDEX_DIR):
            os.makedirs(Config.WHOOSH_INDEX_DIR)

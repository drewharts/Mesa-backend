from typing import Dict, Any, Optional

class SearchResult:
    def __init__(self, 
                 name: str,
                 address: str,
                 latitude: float,
                 longitude: float,
                 place_id: str,
                 source: str,
                 additional_data: Dict[str, Any] = None):
        self.name = name
        self.address = address
        self.latitude = latitude
        self.longitude = longitude
        self.place_id = place_id
        self.source = source
        self.additional_data = additional_data or {} 
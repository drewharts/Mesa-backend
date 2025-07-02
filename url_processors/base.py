from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import re

class URLProcessor(ABC):
    """Base class for URL processors that extract data from various platforms."""
    
    @abstractmethod
    def can_process(self, url: str) -> bool:
        """Check if this processor can handle the given URL."""
        pass
    
    @abstractmethod
    def extract_data(self, url: str) -> Dict[str, Any]:
        """Extract relevant data from the URL."""
        pass
    
    @abstractmethod
    def extract_location_info(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract location information from the processed data.
        
        Returns:
            Dict with possible keys:
            - location_name: str
            - coordinates: Tuple[float, float] (lat, lon)
            - address: str
            - raw_text: str (for further processing)
        """
        pass
    
    def validate_url(self, url: str) -> bool:
        """Basic URL validation."""
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        return url_pattern.match(url) is not None
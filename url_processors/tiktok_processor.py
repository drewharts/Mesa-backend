import re
import requests
from typing import Dict, Any, Optional
from .base import URLProcessor
import logging
import os

logger = logging.getLogger(__name__)

class TikTokProcessor(URLProcessor):
    """Processor for TikTok URLs to extract video metadata and location information."""
    
    def __init__(self):
        self.api_key = os.environ.get('TIKTOK_API_KEY')
        self.base_url = "https://api.tiktok.com/v1"
        
    def can_process(self, url: str) -> bool:
        """Check if URL is a TikTok URL."""
        tiktok_patterns = [
            r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
            r'https?://(?:www\.)?tiktok\.com/t/[\w]+',
            r'https?://vm\.tiktok\.com/[\w]+',
        ]
        return any(re.match(pattern, url) for pattern in tiktok_patterns)
    
    def extract_data(self, url: str) -> Dict[str, Any]:
        """Extract video data from TikTok URL.
        
        Note: This is a placeholder implementation. 
        Actual TikTok API integration would require proper authentication
        and API endpoints which vary based on access level.
        """
        if not self.validate_url(url):
            raise ValueError("Invalid URL format")
            
        if not self.can_process(url):
            raise ValueError("URL is not a valid TikTok URL")
        
        # Extract video ID from URL
        video_id = self._extract_video_id(url)
        
        # In a real implementation, this would call TikTok's API
        # For now, returning a structured response format
        return {
            "video_id": video_id,
            "url": url,
            "caption": "",
            "location": None,
            "hashtags": [],
            "created_at": None,
            "author": {
                "username": "",
                "display_name": ""
            }
        }
    
    def extract_location_info(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract location information from TikTok video data."""
        location_info = {}
        
        # Check if location data is directly available
        if data.get("location"):
            location = data["location"]
            if isinstance(location, dict):
                location_info["location_name"] = location.get("name", "")
                if location.get("latitude") and location.get("longitude"):
                    location_info["coordinates"] = (
                        float(location["latitude"]), 
                        float(location["longitude"])
                    )
                if location.get("address"):
                    location_info["address"] = location["address"]
        
        # Extract location from caption using regex patterns
        if data.get("caption"):
            caption = data["caption"]
            location_info["raw_text"] = caption
            
            # Look for location patterns in caption
            location_patterns = [
                r'📍\s*([^#\n]+)',  # Pin emoji followed by location
                r'(?:at|in|from)\s+([A-Z][^,#\n]{2,})',  # "at/in/from" followed by capitalized words
                r'#(\w+(?:city|place|location|travel))',  # Location-related hashtags
            ]
            
            for pattern in location_patterns:
                matches = re.findall(pattern, caption, re.IGNORECASE)
                if matches and not location_info.get("location_name"):
                    location_info["location_name"] = matches[0].strip()
                    break
        
        return location_info if location_info else None
    
    def _extract_video_id(self, url: str) -> str:
        """Extract video ID from various TikTok URL formats."""
        # Direct video URL
        match = re.search(r'/video/(\d+)', url)
        if match:
            return match.group(1)
        
        # Short URL - would need to be resolved
        match = re.search(r'/t/([\w]+)', url)
        if match:
            return match.group(1)
        
        # VM short URL
        match = re.search(r'vm\.tiktok\.com/([\w]+)', url)
        if match:
            return match.group(1)
        
        raise ValueError("Could not extract video ID from URL")
import re
import requests
from typing import Dict, Any, Optional
from .base import URLProcessor
import logging
import os
import time
import hashlib
import urllib.parse

logger = logging.getLogger(__name__)

class TikTokProcessor(URLProcessor):
    """Processor for TikTok URLs to extract video metadata and location information."""
    
    def __init__(self):
        # TikTok API credentials
        self.client_key = os.environ.get('TIKTOK_CLIENT_KEY')
        self.client_secret = os.environ.get('TIKTOK_CLIENT_SECRET')
        self.access_token = os.environ.get('TIKTOK_ACCESS_TOKEN')
        
        # API endpoints
        self.base_url = "https://open.tiktokapis.com/v2"
        self.video_query_url = f"{self.base_url}/video/query/"
        
        # For public web API (alternative approach)
        self.oembed_url = "https://www.tiktok.com/oembed"
        
    def can_process(self, url: str) -> bool:
        """Check if URL is a TikTok URL."""
        tiktok_patterns = [
            r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+',
            r'https?://(?:www\.)?tiktok\.com/t/[\w]+',
            r'https?://vm\.tiktok\.com/[\w]+',
        ]
        return any(re.match(pattern, url) for pattern in tiktok_patterns)
    
    def extract_data(self, url: str) -> Dict[str, Any]:
        """Extract video data from TikTok URL using available APIs."""
        if not self.validate_url(url):
            raise ValueError("Invalid URL format")
            
        if not self.can_process(url):
            raise ValueError("URL is not a valid TikTok URL")
        
        # First, try the oEmbed API (doesn't require authentication)
        try:
            oembed_data = self._fetch_oembed_data(url)
            if oembed_data:
                logger.info(f"Successfully fetched oEmbed data for URL: {url}")
                
                # Extract basic info from oEmbed
                result = {
                    "video_id": self._extract_video_id(url),
                    "url": url,
                    "title": oembed_data.get("title", ""),
                    "author": {
                        "username": oembed_data.get("author_name", ""),
                        "display_name": oembed_data.get("author_name", ""),
                        "url": oembed_data.get("author_url", "")
                    },
                    "thumbnail_url": oembed_data.get("thumbnail_url", ""),
                    "embed_html": oembed_data.get("html", "")
                }
                
                # Try to extract location from title/description
                result["caption"] = oembed_data.get("title", "")
                result["location"] = None  # oEmbed doesn't provide location
                result["hashtags"] = self._extract_hashtags(result["caption"])
                
                # If we have API credentials, try to get more detailed info
                if self.access_token:
                    detailed_data = self._fetch_video_details(url)
                    if detailed_data:
                        result.update(detailed_data)
                
                return result
                
        except Exception as e:
            logger.error(f"Error fetching oEmbed data: {str(e)}")
        
        # Fallback: If oEmbed fails and we have API credentials, use the official API
        if self.access_token:
            try:
                return self._fetch_video_details(url)
            except Exception as e:
                logger.error(f"Error fetching video details from official API: {str(e)}")
        
        # Final fallback: return basic structure
        logger.warning(f"Could not fetch real data for URL: {url}")
        return {
            "video_id": self._extract_video_id(url),
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
    
    def _fetch_oembed_data(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch data using TikTok's oEmbed API (no auth required)."""
        try:
            params = {"url": url}
            response = requests.get(self.oembed_url, params=params, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"oEmbed API returned status {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error calling oEmbed API: {str(e)}")
            return None
    
    def _fetch_video_details(self, url: str) -> Dict[str, Any]:
        """Fetch detailed video data using TikTok's official API (requires auth)."""
        if not self.access_token:
            raise ValueError("TikTok API access token not configured")
        
        video_id = self._extract_video_id(url)
        
        # TikTok API v2 request
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Query fields we want
        fields = [
            "id", "title", "description", "create_time",
            "music", "author", "statistics", "cover",
            "share_url", "embed_link", "caption", "poi_info"
        ]
        
        params = {
            "fields": ",".join(fields)
        }
        
        try:
            # Note: The exact endpoint and request format depends on your API access level
            # This is based on TikTok's Content Posting API
            response = requests.post(
                self.video_query_url,
                headers=headers,
                json={"video_ids": [video_id]},
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                videos = data.get("videos", [])
                
                if videos:
                    video = videos[0]
                    return {
                        "video_id": video.get("id", video_id),
                        "url": video.get("share_url", url),
                        "caption": video.get("caption", video.get("description", "")),
                        "location": self._extract_location_from_poi(video.get("poi_info")),
                        "hashtags": self._extract_hashtags(video.get("caption", "")),
                        "created_at": video.get("create_time"),
                        "author": {
                            "username": video.get("author", {}).get("username", ""),
                            "display_name": video.get("author", {}).get("display_name", "")
                        },
                        "statistics": video.get("statistics", {}),
                        "music": video.get("music", {}),
                        "thumbnail_url": video.get("cover", {}).get("url", "")
                    }
            else:
                logger.error(f"TikTok API returned status {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Error calling TikTok API: {str(e)}")
            
        raise Exception("Failed to fetch video details from TikTok API")
    
    def _extract_location_from_poi(self, poi_info: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Extract location data from POI (Point of Interest) info."""
        if not poi_info:
            return None
            
        return {
            "name": poi_info.get("name", ""),
            "address": poi_info.get("address", ""),
            "latitude": poi_info.get("latitude"),
            "longitude": poi_info.get("longitude"),
            "city": poi_info.get("city", ""),
            "country": poi_info.get("country", "")
        }
    
    def _extract_hashtags(self, text: str) -> list:
        """Extract hashtags from text."""
        if not text:
            return []
        hashtags = re.findall(r'#(\w+)', text)
        return list(set(hashtags))  # Remove duplicates
    
    def extract_location_info(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract location information from TikTok video data."""
        location_info = {}
        
        # Check if location data is directly available (from poi_info)
        if data.get("location"):
            location = data["location"]
            if isinstance(location, dict) and location.get("name"):
                location_info["location_name"] = location.get("name", "")
                if location.get("latitude") and location.get("longitude"):
                    location_info["coordinates"] = (
                        float(location["latitude"]), 
                        float(location["longitude"])
                    )
                if location.get("address"):
                    location_info["address"] = location["address"]
                if location.get("city"):
                    location_info["city"] = location["city"]
                if location.get("country"):
                    location_info["country"] = location["country"]
        
        # If no direct location, try to extract from caption/title
        caption = data.get("caption") or data.get("title", "")
        if caption and not location_info.get("location_name"):
            location_info["raw_text"] = caption
            
            # Look for location patterns in caption
            location_patterns = [
                (r'📍\s*([^\.#\n]+?)(?:\.\.\.|#|\n|$)', 'pin'),  # Pin emoji followed by location
                (r'(?:at|in|from)\s+([A-Z][^,#\n.!?]{2,30})(?:\s|#|$)', 'preposition'),  # "at/in/from" followed by capitalized words
                (r'#([a-zA-Z]+(?:city|place|location|travel))', 'hashtag'),  # Location-related hashtags
            ]
            
            for pattern, pattern_type in location_patterns:
                matches = re.findall(pattern, caption, re.IGNORECASE)
                if matches:
                    location_info["location_name"] = matches[0].strip()
                    logger.debug(f"Found location '{location_info['location_name']}' using {pattern_type} pattern")
                    break
        
        # Only return location_info if we actually found something meaningful
        if location_info.get("location_name") or location_info.get("coordinates"):
            return location_info
        
        return None
    
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
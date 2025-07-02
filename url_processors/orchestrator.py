from typing import Dict, Any, List, Optional
from .base import URLProcessor
from .tiktok_processor import TikTokProcessor
import logging

logger = logging.getLogger(__name__)

class URLProcessorOrchestrator:
    """Orchestrates multiple URL processors to handle various platforms."""
    
    def __init__(self):
        self.processors: List[URLProcessor] = [
            TikTokProcessor(),
            # Add more processors here as needed
            # InstagramProcessor(),
            # YouTubeProcessor(),
            # etc.
        ]
    
    def process_url(self, url: str) -> Dict[str, Any]:
        """Process a URL using the appropriate processor.
        
        Returns:
            Dict containing:
            - processor_type: str (e.g., "tiktok", "instagram")
            - data: Dict[str, Any] (extracted data)
            - location_info: Optional[Dict[str, Any]] (extracted location)
        """
        # Find appropriate processor
        processor = None
        for p in self.processors:
            if p.can_process(url):
                processor = p
                break
        
        if not processor:
            raise ValueError(f"No processor available for URL: {url}")
        
        # Extract data
        try:
            data = processor.extract_data(url)
            location_info = processor.extract_location_info(data)
            
            return {
                "processor_type": processor.__class__.__name__.replace("Processor", "").lower(),
                "data": data,
                "location_info": location_info
            }
        except Exception as e:
            logger.error(f"Error processing URL {url}: {str(e)}", exc_info=True)
            raise
    
    def get_supported_platforms(self) -> List[str]:
        """Get list of supported platforms."""
        return [
            p.__class__.__name__.replace("Processor", "").lower() 
            for p in self.processors
        ]
#!/usr/bin/env python3
"""Direct test of URL processor without Flask."""

from url_processors.orchestrator import URLProcessorOrchestrator
from url_processors.geocoding_service import GeocodingService
import json

def test_url_processor():
    print("Testing URL Processor directly...")
    
    # Initialize
    orchestrator = URLProcessorOrchestrator()
    
    # Test supported platforms
    platforms = orchestrator.get_supported_platforms()
    print(f"Supported platforms: {platforms}")
    
    # Test TikTok URL processing
    test_urls = [
        "https://www.tiktok.com/@user/video/123456789",
        "https://vm.tiktok.com/ZM8abcdef/",
        "https://example.com/test"  # Should fail
    ]
    
    for url in test_urls:
        print(f"\nTesting URL: {url}")
        try:
            result = orchestrator.process_url(url)
            print(f"Success! Processor: {result['processor_type']}")
            print(f"Data: {json.dumps(result['data'], indent=2)}")
            print(f"Location info: {result['location_info']}")
        except ValueError as e:
            print(f"Expected error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")

if __name__ == "__main__":
    test_url_processor()